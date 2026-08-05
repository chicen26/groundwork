"""Address suggestions and ZIP centroids, from Photon, cached like every other external call.

Photon (photon.komoot.io) is the one geocoder that is free, keyless, and explicitly built for
search-as-you-type, which the Census geocoder is not. It answers two questions for us:

* "What addresses could this half-typed string mean?" — the dropdown under the address field.
* "Where, roughly, is this ZIP code?" — the centroid behind the no-address quick look.

Both degrade rather than fail: suggestions become an empty list, and a quick look becomes an
actionable error telling the user to type a full address. Results are cached in `feed_cache`
(governing principle 3), so a repeated keystroke or a popular ZIP never leaves our network twice.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

import asyncpg
import certifi

PHOTON_ENDPOINT = "https://photon.komoot.io/api"
SUGGEST_CACHE_SOURCE = "photon_suggest"
ZIP_CACHE_SOURCE = "photon_zip"
REQUEST_TIMEOUT_S = 5
SUGGESTION_LIMIT = 6

# Bias results toward the middle of California without excluding the rest of the US: the app is
# California-first but the advisory base covers every state.
_BIAS_LAT, _BIAS_LNG = 37.2, -119.5

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class SuggestionsUnavailable(RuntimeError):
    """Photon could not be reached or returned nothing usable."""


@dataclass(frozen=True)
class AddressSuggestion:
    label: str
    lat: float
    lng: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ZipCentroid:
    zip: str
    place: str | None
    state_code: str | None
    lat: float
    lng: float


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def _fetch_features(params: dict[str, str | int | float]) -> list[dict]:
    query = urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(
            f"{PHOTON_ENDPOINT}?{query}", timeout=REQUEST_TIMEOUT_S, context=_SSL_CONTEXT
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SuggestionsUnavailable(f"photon unreachable: {exc}") from exc
    return payload.get("features") or []


def _label(properties: dict) -> str | None:
    """One human-readable line per suggestion, built from whatever parts Photon returned."""
    street = properties.get("street") or properties.get("name")
    if not street:
        return None
    house = properties.get("housenumber")
    first = f"{house} {street}" if house else street

    locality = properties.get("city") or properties.get("district") or properties.get("county")
    state = properties.get("state")
    postcode = properties.get("postcode")

    parts = [first]
    if locality:
        parts.append(locality)
    if state:
        parts.append(f"{state} {postcode}" if postcode else state)
    return ", ".join(parts)


def _request_suggestions(text: str) -> list[AddressSuggestion]:
    features = _fetch_features(
        {
            "q": text,
            "limit": SUGGESTION_LIMIT * 2,  # room to drop non-US and unlabelable results
            "lang": "en",
            "lat": _BIAS_LAT,
            "lon": _BIAS_LNG,
            # Weight proximity to the bias point well above Photon's default, or a Californian
            # typing a common street name sees five other states first.
            "zoom": 8,
            "location_bias_scale": 0.5,
        }
    )

    suggestions: list[AddressSuggestion] = []
    seen: set[str] = set()
    for feature in features:
        properties = feature.get("properties") or {}
        if (properties.get("countrycode") or "").upper() != "US":
            continue
        label = _label(properties)
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if not label or len(coordinates) != 2 or label in seen:
            continue
        seen.add(label)
        suggestions.append(
            AddressSuggestion(label=label, lat=float(coordinates[1]), lng=float(coordinates[0]))
        )
        if len(suggestions) == SUGGESTION_LIMIT:
            break
    return suggestions


# The five-digit ZIP is embedded in a fuller query because Photon ranks a bare number poorly.
def _request_zip(zip_code: str) -> ZipCentroid:
    features = _fetch_features(
        {
            "q": f"{zip_code} United States",
            "osm_tag": "place:postcode",
            "limit": 5,
            "lang": "en",
            "lat": _BIAS_LAT,
            "lon": _BIAS_LNG,
        }
    )

    for feature in features:
        properties = feature.get("properties") or {}
        if (properties.get("countrycode") or "").upper() != "US":
            continue
        if (properties.get("postcode") or properties.get("name")) != zip_code:
            continue
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) != 2:
            continue
        state = properties.get("state")
        return ZipCentroid(
            zip=zip_code,
            place=properties.get("city") or properties.get("district") or properties.get("county"),
            # Photon gives the state's full name; two-letter codes are what the rules engine keys
            # on, so translate only the ones we can and leave the rest honestly unknown.
            state_code=_STATE_CODES.get((state or "").lower()),
            lat=float(coordinates[1]),
            lng=float(coordinates[0]),
        )
    raise SuggestionsUnavailable(f"no US place found for ZIP {zip_code}")


async def _cached(conn: asyncpg.Connection, source: str, key: str) -> dict | list | None:
    payload = await conn.fetchval(
        "SELECT payload FROM feed_cache WHERE source = $1 AND cache_key = $2", source, key
    )
    if payload is None:
        return None
    return json.loads(payload) if isinstance(payload, str) else payload


async def _store(conn: asyncpg.Connection, source: str, key: str, payload: dict | list) -> None:
    await conn.execute(
        """
        INSERT INTO feed_cache (source, cache_key, payload)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (source, cache_key)
        DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()
        """,
        source,
        key,
        json.dumps(payload),
    )


async def suggest_addresses(conn: asyncpg.Connection, text: str) -> list[AddressSuggestion]:
    """Suggestions for a partial address. Failure is an empty list, never an error — a dropdown
    that sometimes stays closed is fine; an address field that shows errors while typing is not."""
    key = _normalize(text)

    cached = await _cached(conn, SUGGEST_CACHE_SOURCE, key)
    if cached is not None:
        return [AddressSuggestion(**item) for item in cached]

    try:
        suggestions = await asyncio.to_thread(_request_suggestions, text)
    except SuggestionsUnavailable:
        return []

    await _store(conn, SUGGEST_CACHE_SOURCE, key, [s.as_dict() for s in suggestions])
    return suggestions


async def zip_centroid(conn: asyncpg.Connection, zip_code: str) -> ZipCentroid:
    """Where a ZIP roughly is. Raises SuggestionsUnavailable when we cannot place it."""
    cached = await _cached(conn, ZIP_CACHE_SOURCE, zip_code)
    if cached is not None:
        return ZipCentroid(**cached)

    centroid = await asyncio.to_thread(_request_zip, zip_code)
    await _store(conn, ZIP_CACHE_SOURCE, zip_code, asdict(centroid))
    return centroid


_STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}  # fmt: skip
