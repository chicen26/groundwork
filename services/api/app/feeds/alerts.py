"""The context strip: Red Flag Warnings, served from our cache.

Governing principle 3, in its most literal form. The National Weather Service is fetched by a
scheduled refresh into `feed_cache`, and a request reads only from there. If NWS is slow or down,
the strip reports that it has no current information — it never blocks a scan, and no demo depends
on somebody else's uptime.

Deliberately minimal. One strip, no map screen, and nothing resembling evacuation guidance.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import certifi

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
CACHE_SOURCE = "nws_alerts"
# NWS asks for a contact in the user agent; being identifiable is also just good manners.
USER_AGENT = "Groundwork/0.1 (Congressional App Challenge project; contact via GitHub chicen26)"
REQUEST_TIMEOUT_S = 10
FRESH_FOR = timedelta(minutes=15)

# The event names worth interrupting someone's screen for.
ELEVATED_EVENTS = {"Red Flag Warning", "Fire Weather Watch", "Extreme Fire Danger"}

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class AlertStrip:
    """What the strip shows. `available` false means we do not know, not that all is well."""

    available: bool
    red_flag: bool
    events: list[str]
    headline: str | None
    fetched_at: datetime | None

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "red_flag": self.red_flag,
            "events": self.events,
            "headline": self.headline,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            # Said out loud, because a fire-adjacent app showing weather could easily be mistaken
            # for something operational.
            "note": (
                "Weather information only, from the National Weather Service. Groundwork does not "
                "provide evacuation guidance — follow your fire agency and local law enforcement."
            ),
        }


def _cache_key(lat: float, lng: float) -> str:
    """Round to ~1 km. Alert areas are counties and zones; a per-metre key would never hit."""
    return f"{lat:.2f},{lng:.2f}"


def fetch_alerts(lat: float, lng: float) -> dict:
    """Fetch from NWS. Only the scheduled refresh calls this — never a request handler."""
    request = urllib.request.Request(
        f"{NWS_ALERTS_URL}?point={lat:.4f},{lng:.4f}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
    )
    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT_S, context=_SSL_CONTEXT
    ) as response:
        return json.load(response)


def summarise(payload: dict) -> tuple[bool, list[str], str | None]:
    events: list[str] = []
    headline: str | None = None

    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        event = properties.get("event")
        if event:
            events.append(event)
            if event in ELEVATED_EVENTS and headline is None:
                headline = properties.get("headline") or event

    return (any(e in ELEVATED_EVENTS for e in events), sorted(set(events)), headline)


async def refresh(conn: asyncpg.Connection, lat: float, lng: float) -> AlertStrip:
    """Fetch and cache. Called by the scheduled job, and by nothing on the request path."""
    payload = fetch_alerts(lat, lng)
    red_flag, events, headline = summarise(payload)

    await conn.execute(
        """
        INSERT INTO feed_cache (source, cache_key, payload, expires_at)
        VALUES ($1, $2, $3::jsonb, now() + interval '1 hour')
        ON CONFLICT (source, cache_key)
        DO UPDATE SET payload = EXCLUDED.payload, fetched_at = now(),
                      expires_at = EXCLUDED.expires_at
        """,
        CACHE_SOURCE,
        _cache_key(lat, lng),
        json.dumps({"red_flag": red_flag, "events": events, "headline": headline}),
    )
    return AlertStrip(
        available=True,
        red_flag=red_flag,
        events=events,
        headline=headline,
        fetched_at=datetime.now(UTC),
    )


async def read_cached(conn: asyncpg.Connection, lat: float, lng: float) -> AlertStrip:
    """What the strip shows, from cache only.

    A miss, or a stale entry, returns `available=False`. That is honest and harmless: the strip
    simply does not render. The alternative — blocking on a live fetch — would put somebody else's
    server on the critical path of a scan.
    """
    row = await conn.fetchrow(
        "SELECT payload, fetched_at FROM feed_cache WHERE source = $1 AND cache_key = $2",
        CACHE_SOURCE,
        _cache_key(lat, lng),
    )
    if row is None:
        return AlertStrip(
            available=False, red_flag=False, events=[], headline=None, fetched_at=None
        )

    fetched_at = row["fetched_at"]
    if fetched_at and datetime.now(UTC) - fetched_at > FRESH_FOR:
        # Stale weather presented as current is worse than none: someone could read a cleared Red
        # Flag Warning as still in force, or the reverse.
        return AlertStrip(
            available=False, red_flag=False, events=[], headline=None, fetched_at=fetched_at
        )

    payload = row["payload"]
    data = json.loads(payload) if isinstance(payload, str) else payload
    return AlertStrip(
        available=True,
        red_flag=bool(data.get("red_flag")),
        events=list(data.get("events", [])),
        headline=data.get("headline"),
        fetched_at=fetched_at,
    )
