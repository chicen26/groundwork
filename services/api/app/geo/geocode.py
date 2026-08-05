"""Address to coordinate, with the external call kept off the critical path.

We use the US Census Bureau geocoder: free, no key, no per-request terms to violate, and its
coverage is exactly the US addresses we care about.

Geocoding is the one place we cannot pre-cache a third-party call, since the input is whatever
address the user just typed. Two things keep governing principle 3 intact anyway:

* Results are cached in `feed_cache`, so a repeated address never leaves our network.
* The client can supply coordinates directly (a dropped map pin or device location), and the demo
  path does exactly that. If the geocoder is slow or down, address entry degrades to "place your
  home on the map" rather than failing.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import asyncpg
import certifi

CENSUS_ENDPOINT = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
CACHE_SOURCE = "census_geocoder"
REQUEST_TIMEOUT_S = 8

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class GeocodingUnavailable(RuntimeError):
    """The geocoder could not be reached or returned nothing usable."""


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    matched_address: str
    # Two-letter state code, when the geocoder gave us one. Decides which statutory rules apply.
    state_code: str | None = None
    cached: bool = False


def _normalize(address: str) -> str:
    """Cache key: whitespace and case should not produce two entries for one address."""
    return " ".join(address.split()).lower()


def _request(address: str) -> GeocodeResult:
    query = urllib.parse.urlencode(
        {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    )
    try:
        with urllib.request.urlopen(
            f"{CENSUS_ENDPOINT}?{query}", timeout=REQUEST_TIMEOUT_S, context=_SSL_CONTEXT
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeocodingUnavailable(f"census geocoder unreachable: {exc}") from exc

    matches = payload.get("result", {}).get("addressMatches") or []
    if not matches:
        raise GeocodingUnavailable("no match for that address")

    best = matches[0]
    coordinates = best.get("coordinates", {})
    components = best.get("addressComponents") or {}
    state = (components.get("state") or "").strip().upper() or None
    try:
        return GeocodeResult(
            lat=float(coordinates["y"]),
            lng=float(coordinates["x"]),
            matched_address=best.get("matchedAddress", address),
            state_code=state if state and len(state) == 2 else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodingUnavailable("geocoder returned an unusable match") from exc


async def geocode(conn: asyncpg.Connection, address: str) -> GeocodeResult:
    """Geocode an address, preferring our cache. Raises GeocodingUnavailable on failure."""
    key = _normalize(address)

    cached = await conn.fetchval(
        "SELECT payload FROM feed_cache WHERE source = $1 AND cache_key = $2",
        CACHE_SOURCE,
        key,
    )
    if cached:
        data = json.loads(cached) if isinstance(cached, str) else cached
        return GeocodeResult(
            lat=data["lat"],
            lng=data["lng"],
            matched_address=data["matched_address"],
            state_code=data.get("state_code"),
            cached=True,
        )

    # The geocoder call is blocking; keep it off the event loop so one slow lookup cannot stall
    # every other request the service is handling.
    result = await asyncio.to_thread(_request, address)

    await conn.execute(
        """
        INSERT INTO feed_cache (source, cache_key, payload)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (source, cache_key)
        DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now()
        """,
        CACHE_SOURCE,
        key,
        json.dumps(
            {
                "lat": result.lat,
                "lng": result.lng,
                "matched_address": result.matched_address,
                "state_code": result.state_code,
            }
        ),
    )
    return result
