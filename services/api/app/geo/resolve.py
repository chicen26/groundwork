"""Point-in-polygon resolution against our hosted boundary layers.

Given a coordinate, answer three questions: which fire hazard severity zone, whose fire district,
whose water utility. Each answer names the published map it came from, and each is allowed to be
"not determined" — a property outside every imported polygon gets an honest gap rather than a
nearest-neighbour guess.

Only the active version of each layer is consulted, so an import in progress never leaks
half-loaded geometry into someone's assessment.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

# A property is resolved against LRA first: where both maps cover a point, the local map is the one
# that governs it, and the state layer is the fallback for unincorporated land.
_FHSZ_QUERY = """
SELECT z.fhsz::text AS fhsz,
       z.responsibility,
       v.source_version
FROM fhsz_zones z
JOIN gis_layer_versions v ON v.id = z.layer_version_id AND v.is_active
WHERE ST_Contains(z.geom, ST_SetSRID(ST_MakePoint($1, $2), 4326))
ORDER BY CASE z.responsibility WHEN 'LRA' THEN 0 WHEN 'SRA' THEN 1 ELSE 2 END
LIMIT 1
"""

_DISTRICT_QUERY = """
SELECT d.name, d.agency_code, v.source_version
FROM fire_districts d
JOIN gis_layer_versions v ON v.id = d.layer_version_id AND v.is_active
WHERE ST_Contains(d.geom, ST_SetSRID(ST_MakePoint($1, $2), 4326))
LIMIT 1
"""

_UTILITY_QUERY = """
SELECT u.name, u.utility_code, v.source_version
FROM water_utilities u
JOIN gis_layer_versions v ON v.id = u.layer_version_id AND v.is_active
WHERE ST_Contains(u.geom, ST_SetSRID(ST_MakePoint($1, $2), 4326))
LIMIT 1
"""


@dataclass(frozen=True)
class GeoResolution:
    """What we could determine about a location, and from which published maps."""

    fhsz: str = "unknown"
    fhsz_responsibility: str | None = None
    fhsz_source_version: str | None = None
    fire_district: str | None = None
    fire_district_source_version: str | None = None
    water_utility: str | None = None
    water_utility_source_version: str | None = None

    @property
    def is_wildland_hazard_zone(self) -> bool:
        """True when the property sits in a designated hazard zone that carries obligations."""
        return self.fhsz in {"moderate", "high", "very_high"}

    @property
    def unresolved(self) -> list[str]:
        """Which answers we could not determine, for the client to surface honestly."""
        missing = []
        if self.fhsz == "unknown":
            missing.append("fhsz")
        if self.fire_district is None:
            missing.append("fire_district")
        if self.water_utility is None:
            missing.append("water_utility")
        return missing


async def resolve_point(conn: asyncpg.Connection, *, lat: float, lng: float) -> GeoResolution:
    """Resolve one coordinate against every active boundary layer."""
    fhsz_row = await conn.fetchrow(_FHSZ_QUERY, lng, lat)
    district_row = await conn.fetchrow(_DISTRICT_QUERY, lng, lat)
    utility_row = await conn.fetchrow(_UTILITY_QUERY, lng, lat)

    return GeoResolution(
        fhsz=fhsz_row["fhsz"] if fhsz_row else "unknown",
        fhsz_responsibility=fhsz_row["responsibility"] if fhsz_row else None,
        fhsz_source_version=fhsz_row["source_version"] if fhsz_row else None,
        fire_district=district_row["name"] if district_row else None,
        fire_district_source_version=district_row["source_version"] if district_row else None,
        water_utility=utility_row["name"] if utility_row else None,
        water_utility_source_version=utility_row["source_version"] if utility_row else None,
    )
