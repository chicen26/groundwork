"""Where our boundary layers come from.

Layer sources are configuration, not code paths: each entry says which ArcGIS service to pull, how
to translate its attributes into our columns, and what to call the edition. Adding a county's fire
district map should mean adding an entry here, not writing a new importer.

Every URL in this file is in the verify-before-launch register. Publishers reorganise services, and
a URL that worked in August is not evidence it works in October.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Import extents. The corridor keeps dev imports fast; the default deployment imports the whole
# state — CAL FIRE's maps are statewide, so serving all of California is a bounding box, not a
# feature. (~28k polygons statewide vs ~800 in the corridor, verified Aug 2026.)
CA10_BBOX = (-122.55, 37.40, -121.40, 38.15)
CALIFORNIA_BBOX = (-124.48, 32.53, -114.13, 42.01)
EXTENTS = {"ca10": CA10_BBOX, "california": CALIFORNIA_BBOX}


def _fhsz_class_from_description(description: str | None) -> str:
    """Map a publisher's zone label onto our `fhsz_class` enum.

    CAL FIRE writes these as 'Very High', 'High', 'Moderate', 'NonWildland'. Anything we do not
    recognise becomes 'unknown' rather than a guess — showing the wrong zone is worse than showing
    none, because the zone decides which legal obligations we tell someone they have.
    """
    normalized = (description or "").strip().lower().replace(" ", "")
    return {
        "veryhigh": "very_high",
        "high": "high",
        "moderate": "moderate",
        "nonwildland": "non_wildland",
    }.get(normalized, "unknown")


@dataclass(frozen=True)
class LayerSource:
    """One importable boundary layer."""

    # Our internal name, matching the target table's role: 'fhsz_lra', 'fhsz_sra', ...
    key: str
    table: str
    url: str
    source_version: str
    # Attributes to request from the service.
    out_fields: tuple[str, ...]
    # Turns one feature's attributes into the non-geometry columns we store.
    attributes: Callable[[dict[str, Any]], dict[str, Any]]
    # False for layers whose URL we have not yet confirmed against the publisher.
    verified: bool = True
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


CALFIRE_ORG = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services"

FHSZ_LRA_2025 = LayerSource(
    key="fhsz_lra",
    table="fhsz_zones",
    url=f"{CALFIRE_ORG}/FHSALRA25_v1_All/FeatureServer/0",
    source_version="CAL FIRE FHSZ in LRA, 2025 v1",
    out_fields=("FHSZ", "FHSZ_Description", "SRA"),
    attributes=lambda a: {
        "responsibility": "LRA",
        "fhsz": _fhsz_class_from_description(a.get("FHSZ_Description")),
    },
    notes=(
        "The February 2025 maps that redrew Very High zones inside 12 Contra Costa cities. "
        "Verified Aug 4, 2026: Lafayette resolves Moderate/LRA, Danville centre NonWildland/LRA."
    ),
)

FHSZ_SRA = LayerSource(
    key="fhsz_sra",
    table="fhsz_zones",
    url=f"{CALFIRE_ORG}/FHSZSRA_23_3/FeatureServer/0",
    source_version="CAL FIRE FHSZ in SRA, 2023 v3",
    out_fields=("FHSZ", "FHSZ_Description", "SRA"),
    attributes=lambda a: {
        "responsibility": "SRA",
        "fhsz": _fhsz_class_from_description(a.get("FHSZ_Description")),
    },
    notes=(
        "State Responsibility Area zones. Properties in the Diablo foothills (e.g. Blackhawk) fall "
        "here rather than in the LRA layer."
    ),
)


def _title_case(raw: str) -> str:
    """SHOUTING publisher attributes, made readable without mangling hyphenated names."""
    return " ".join(
        "-".join(part.capitalize() for part in word.split("-")) for word in raw.lower().split()
    )


# Names the rest of the product already keys on. `resources.json` matches districts by these
# exact names, and `rebates.json` matches utilities by agency code — so the importer speaks
# their language for the agencies we have programmes for, and title-cases everything else.
_DISTRICT_CANONICAL = {
    "SAN RAMON VALLEY FPD": "San Ramon Valley Fire Protection District",
    # The layer abbreviates "County" to "Co"; resources.json speaks the full name.
    "CONTRA COSTA CO FPD": "Contra Costa County Fire Protection District",
    "CONTRA COSTA COUNTY FPD": "Contra Costa County Fire Protection District",
    "MORAGA-ORINDA FPD": "Moraga-Orinda Fire District",
}

_UTILITY_CANONICAL = {
    "EAST BAY MUD": "EBMUD",
    "EAST BAY MUNICIPAL UTILITY DISTRICT": "EBMUD",
    "CONTRA COSTA WATER DISTRICT": "CCWD",
    "DUBLIN SAN RAMON SERVICES DISTRICT": "DSRSD",
}


def _district_name(attributes: dict[str, Any]) -> str:
    raw = (attributes.get("Name") or "").strip()
    if raw.upper() in _DISTRICT_CANONICAL:
        return _DISTRICT_CANONICAL[raw.upper()]
    name = _title_case(raw)
    # Expand the abbreviation the layer uses so screens read like an agency, not a code.
    if name.endswith(" Fpd"):
        name = name[:-4] + " Fire Protection District"
    elif name.endswith(" Fd"):
        name = name[:-3] + " Fire District"
    return name


def _utility_name(attributes: dict[str, Any]) -> str:
    raw = (attributes.get("WATER_SYSTEM_NAME") or "").strip()
    return _UTILITY_CANONICAL.get(raw.upper(), _title_case(raw))


FIRE_DISTRICTS = LayerSource(
    key="fire_districts",
    table="fire_districts",
    url=f"{CALFIRE_ORG}/California_Local_Fire_Districts/FeatureServer/0",
    source_version="CAL FIRE Local Fire Districts, 2026 v1",
    out_fields=("Name", "FDID", "County"),
    attributes=lambda a: {
        "name": _district_name(a),
        "agency_code": (a.get("FDID") or None),
    },
    notes=(
        "CAL FIRE's statewide compilation of local fire district boundaries, updated yearly "
        "against the State Fire Marshal's FDID register. Verified Aug 5, 2026: Danville centre "
        "resolves to San Ramon Valley FPD (FDID 07035)."
    ),
    # District polygons are county-sized and vertex-heavy; smaller pages keep each request
    # comfortably inside the service's timeout.
    extra={"page_size": 50},
)

WATER_UTILITIES = LayerSource(
    key="water_utilities",
    table="water_utilities",
    url=(
        "https://gispublic.waterboards.ca.gov/portalserver/rest/services/Drinking_Water/"
        "California_Drinking_Water_System_Area_Boundaries/FeatureServer/0"
    ),
    source_version="SWRCB Drinking Water System Area Boundaries (SABL), 2026",
    out_fields=("WATER_SYSTEM_NAME", "SABL_PWSID", "BOUNDARY_TYPE"),
    attributes=lambda a: {
        "name": _utility_name(a),
        "utility_code": (a.get("SABL_PWSID") or None),
    },
    notes=(
        "The State Water Board's verified service-area polygons — the same authority the rebate "
        "question needs, since the utility decides rates and caps. Water Service Area boundaries "
        "only: jurisdictional boundaries overstate who a system actually serves. Verified "
        "Aug 5, 2026: Danville centre resolves to EBMUD (CA0110005)."
    ),
    extra={"where": "BOUNDARY_TYPE = 'Water Service Area'", "page_size": 100},
)

SOURCES: dict[str, LayerSource] = {
    source.key: source for source in (FHSZ_LRA_2025, FHSZ_SRA, FIRE_DISTRICTS, WATER_UTILITIES)
}
