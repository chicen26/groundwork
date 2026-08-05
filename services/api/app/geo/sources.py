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

# --- Not yet verified -------------------------------------------------------------------------
#
# Fire district and water utility boundaries are published per-county and per-agency rather than by
# one authority, and Contra Costa's district polygons are not in its public ArcGIS folders. Until a
# source is confirmed, resolution returns "not determined" for these rather than a plausible guess:
# telling someone the wrong fire district sends them to the wrong agency for an inspection.
#
# Open research item, tracked in the verify-before-launch register:
#   * SRVFPD / Con Fire / MOFD / ACFD service-area polygons
#   * EBMUD / CCWD / DSRSD service-area polygons, including the split cities (Walnut Creek and
#     San Ramon are each served by two utilities, so a city-name lookup is not good enough)

SOURCES: dict[str, LayerSource] = {source.key: source for source in (FHSZ_LRA_2025, FHSZ_SRA)}
