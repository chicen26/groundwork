"""Import the plant palette from the published sources.

    python -m scripts.import_plants --file ml/../data/plants.json

Every row must name its sources. A plant recommendation with no citation is a horticultural claim we
are not in a position to make, and Calscape's data specifically requires attribution — so the
importer refuses a row without sources rather than importing it and hoping to add them later.

The joined dataset is assembled from:

* **WUCOLS V** (UC Davis) — water-use rating per taxon, for our region.
* **Calscape** (California Native Plant Society) — native status. Non-commercial use with
  attribution; there is no public API, so this is a curated import.
* **UC ANR and local fire safe council lists** — fire-wise notes and zone suitability.

Nothing here is seeded by hand. Until the imports are run, the palette endpoint honestly returns an
empty list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from app.config import get_settings

WUCOLS_RATINGS = {"very low", "low", "moderate", "high"}
# Never '0-5ft': the draft Zone 0 rule wants that band non-combustible, so no plant belongs there.
VALID_ZONES = {"5-30ft", "30-100ft"}


class PlantImportError(ValueError):
    """A row could not be imported, with the reason."""


def validate(entry: dict, index: int) -> dict:
    where = f"row {index} ({entry.get('scientific_name', 'unnamed')})"

    for field in ("common_name", "scientific_name"):
        if not entry.get(field):
            raise PlantImportError(f"{where}: missing {field}")

    sources = entry.get("sources") or []
    if not sources:
        raise PlantImportError(
            f"{where}: no sources. Every plant must cite where its data came from — "
            "Calscape's terms require attribution, and an uncited recommendation is not one "
            "we can make."
        )

    rating = (entry.get("wucols_rating") or "").lower()
    if rating and rating not in WUCOLS_RATINGS:
        raise PlantImportError(f"{where}: unknown WUCOLS rating {rating!r}")

    zones = entry.get("zones_allowed") or []
    unknown = set(zones) - VALID_ZONES
    if unknown:
        raise PlantImportError(
            f"{where}: zones {sorted(unknown)} are not plantable. "
            "The first five feet is non-combustible under the draft Zone 0 rule."
        )

    return {
        "common_name": entry["common_name"],
        "scientific_name": entry["scientific_name"],
        "wucols_rating": rating or None,
        "fire_notes": entry.get("fire_notes"),
        "native": bool(entry.get("native", False)),
        "sun": entry.get("sun"),
        "zones_allowed": zones,
        "sources": sources,
    }


async def import_plants(dsn: str, path: Path, *, dry_run: bool = False) -> int:
    payload = json.loads(path.read_text())
    rows = [validate(entry, i) for i, entry in enumerate(payload["plants"], start=1)]

    if dry_run:
        return len(rows)

    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            for row in rows:
                await conn.execute(
                    """
                    INSERT INTO plants (common_name, scientific_name, wucols_rating, fire_notes,
                                        native, sun, zones_allowed, sources)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (scientific_name) DO UPDATE SET
                        common_name = EXCLUDED.common_name,
                        wucols_rating = EXCLUDED.wucols_rating,
                        fire_notes = EXCLUDED.fire_notes,
                        native = EXCLUDED.native,
                        sun = EXCLUDED.sun,
                        zones_allowed = EXCLUDED.zones_allowed,
                        sources = EXCLUDED.sources,
                        updated_at = now()
                    """,
                    row["common_name"],
                    row["scientific_name"],
                    row["wucols_rating"],
                    row["fire_notes"],
                    row["native"],
                    row["sun"],
                    row["zones_allowed"],
                    row["sources"],
                )
    finally:
        await conn.close()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsn")
    args = parser.parse_args()

    dsn = args.dsn or get_settings().database_url
    if not dsn and not args.dry_run:
        print("no database URL: set GROUNDWORK_DATABASE_URL or pass --dsn", file=sys.stderr)
        return 2

    try:
        count = asyncio.run(import_plants(dsn or "", args.file, dry_run=args.dry_run))
    except PlantImportError as exc:
        print(f"import refused: {exc}", file=sys.stderr)
        return 1

    print(f"{'validated' if args.dry_run else 'imported'} {count} plants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
