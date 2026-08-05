"""Import boundary layers from their publishers into our PostGIS tables.

    python -m scripts.import_gis --layer fhsz_lra --layer fhsz_sra
    python -m scripts.import_gis --all --dry-run

An import is atomic and versioned: features load into a new `gis_layer_versions` row, and that row
is promoted to active only after every page has landed. A refresh that dies halfway leaves the
previous map serving. This is the only place that writes boundary geometry, and it runs as the
owning role — never as the request-handler role.

Statewide layers are clipped to the CA-10 corridor on request, which is the difference between
hosting tens of megabytes and hosting gigabytes we would never query.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import asyncpg
import certifi

from app.config import get_settings
from app.geo.sources import EXTENTS, SOURCES, LayerSource

PAGE_SIZE = 500
REQUEST_TIMEOUT_S = 120

# Verify TLS against certifi's bundle rather than whatever the host happens to trust.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class ImportError_(RuntimeError):
    """An import could not complete; the previous layer version is left active."""


def _fetch_page(source: LayerSource, offset: int, bbox: tuple[float, float, float, float]) -> dict:
    page_size = source.extra.get("page_size", PAGE_SIZE)
    query = {
        "where": source.extra.get("where", "1=1"),
        "outFields": ",".join(source.out_fields),
        "geometry": ",".join(str(v) for v in bbox),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
        "f": "geojson",
    }
    url = f"{source.url}/query?{urllib.parse.urlencode(query)}"

    try:
        with urllib.request.urlopen(
            url, timeout=REQUEST_TIMEOUT_S, context=_SSL_CONTEXT
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ImportError_(f"{source.key}: fetching offset {offset} failed: {exc}") from exc

    # ArcGIS reports errors with HTTP 200 and an error body, so a successful request proves nothing.
    if "error" in payload:
        raise ImportError_(f"{source.key}: service returned an error: {payload['error']}")
    return payload


def fetch_features(
    source: LayerSource, bbox: tuple[float, float, float, float]
) -> list[dict[str, Any]]:
    """Page through a feature service until it stops handing back features."""
    features: list[dict[str, Any]] = []
    offset = 0
    page_size = source.extra.get("page_size", PAGE_SIZE)

    while True:
        payload = _fetch_page(source, offset, bbox)
        page = payload.get("features") or []
        features.extend(page)
        print(f"  {source.key}: {len(features)} features", file=sys.stderr)

        # Two ways a service says "that was the last page"; honour both, and stop on a short page
        # so a service that ignores exceededTransferLimit cannot loop us forever.
        if not payload.get("properties", {}).get("exceededTransferLimit") and not payload.get(
            "exceededTransferLimit"
        ):
            break
        if len(page) < page_size:
            break
        offset += page_size

    return features


async def load(conn: asyncpg.Connection, source: LayerSource, features: list[dict]) -> int:
    """Load one layer's features as a new version, then promote it. All or nothing."""
    if not features:
        raise ImportError_(f"{source.key}: publisher returned no features; refusing to import")

    async with conn.transaction():
        version_id = await conn.fetchval(
            """
            INSERT INTO gis_layer_versions (layer, source_url, source_version, feature_count)
            VALUES ($1, $2, $3, $4) RETURNING id
            """,
            source.key,
            source.url,
            source.source_version,
            len(features),
        )

        loaded = 0
        for feature in features:
            geometry = feature.get("geometry")
            if not geometry:
                continue
            columns = source.attributes(feature.get("properties") or {})

            names = ["layer_version_id", *columns.keys(), "geom"]
            placeholders = [f"${i + 1}" for i in range(len(columns) + 1)]
            # ST_Multi normalises Polygon and MultiPolygon into one column type; ST_MakeValid
            # repairs the self-intersections that occasionally survive publication.
            geom_sql = f"ST_Multi(ST_MakeValid(ST_GeomFromGeoJSON(${len(columns) + 2})))"

            await conn.execute(
                f"INSERT INTO {source.table} ({', '.join(names)}) "
                f"VALUES ({', '.join(placeholders)}, {geom_sql})",
                version_id,
                *columns.values(),
                json.dumps(geometry),
            )
            loaded += 1

        if loaded == 0:
            raise ImportError_(f"{source.key}: every feature lacked geometry")

        # Promote last: until this runs, resolution keeps using the previous version.
        await conn.execute(
            "UPDATE gis_layer_versions SET is_active = false WHERE layer = $1 AND is_active",
            source.key,
        )
        await conn.execute(
            "UPDATE gis_layer_versions SET is_active = true, feature_count = $2 WHERE id = $1",
            version_id,
            loaded,
        )

        # Old versions are kept for one generation so a bad import can be rolled back by hand, and
        # anything older is dropped to stop the table growing without bound.
        await conn.execute(
            """
            DELETE FROM gis_layer_versions
            WHERE layer = $1 AND NOT is_active AND id <> (
                SELECT id FROM gis_layer_versions
                WHERE layer = $1 AND NOT is_active
                ORDER BY imported_at DESC LIMIT 1
            )
            """,
            source.key,
        )

    return loaded


async def import_layers(
    dsn: str, keys: list[str], *, bbox=None, dry_run: bool = False
) -> dict[str, int]:
    results: dict[str, int] = {}
    conn = await asyncpg.connect(dsn)
    try:
        for key in keys:
            source = SOURCES[key]
            print(f"{source.key}: fetching from {source.url}", file=sys.stderr)
            features = fetch_features(source, bbox or EXTENTS["california"])
            if dry_run:
                print(f"  {source.key}: dry run, {len(features)} features not loaded")
                results[key] = 0
                continue
            results[key] = await load(conn, source, features)
            print(f"  {source.key}: loaded {results[key]} features and promoted to active")
    finally:
        await conn.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", action="append", choices=sorted(SOURCES), default=[])
    parser.add_argument("--all", action="store_true", help="import every configured layer")
    parser.add_argument("--dry-run", action="store_true", help="fetch but do not write")
    parser.add_argument(
        "--extent",
        choices=sorted(EXTENTS),
        default="california",
        help="california (default) imports the whole state; ca10 is the fast dev corridor",
    )
    parser.add_argument("--dsn", help="override GROUNDWORK_DATABASE_URL")
    args = parser.parse_args()

    keys = sorted(SOURCES) if args.all else args.layer
    if not keys:
        parser.error("choose --layer or --all")

    dsn = args.dsn or get_settings().database_url
    if not dsn:
        print("no database URL: set GROUNDWORK_DATABASE_URL or pass --dsn", file=sys.stderr)
        return 2

    try:
        asyncio.run(import_layers(dsn, keys, bbox=EXTENTS[args.extent], dry_run=args.dry_run))
    except ImportError_ as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
