"""Harvest openly-licensed training images from the web.

    python -m ml.harvest --out ml/data/harvested --per-query 60

Halves the collection problem: the web can supply the common classes (dead vegetation, overhanging
limbs, cluttered decks) in volume, leaving our own camera for what it cannot — the Zone 0 band,
where "bark mulch against a foundation" and "wooden fence meeting a wall" are not what anyone
photographs for a gardening blog.

Two rules, enforced rather than intended:

* **Licence or it does not land.** Every image is written with its licence, source URL, and creator.
  An image whose licence we cannot record is skipped, because the dataset is going to be published
  and an unattributable image would make that impossible.
* **No scraping of sources that forbid it.** Openverse and Wikimedia Commons index openly-licensed
  work and offer real APIs. Google Images and Street View are never touched — Street View's terms
  prohibit it outright, and using it would compromise the dataset release.

Harvested images are *candidates*. They still pass through `ml/autolabel.py` and then a human, and
they still split by property (each source image is its own "property", so no near-duplicate pair
straddles the train/test line).
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

import certifi

OPENVERSE_API = "https://api.openverse.org/v1/images/"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "Groundwork/0.1 (student project; https://github.com/chicen26/groundwork)"
REQUEST_TIMEOUT_S = 30
# Be a good citizen of two free APIs run for the public benefit.
PAUSE_BETWEEN_REQUESTS_S = 1.0

_SSL = ssl.create_default_context(cafile=certifi.where())

# Licences we can republish under, with attribution. Deliberately excludes ND (no derivatives —
# cropping and augmenting for training is a derivative) and anything without a clear grant.
ACCEPTABLE_LICENCES = {"cc0", "pdm", "by", "by-sa"}

# What to search for, per class. Phrased as a photographer would tag a picture, not as our taxonomy
# names it — "dead shrub" finds photographs, "dead_vegetation" finds nothing.
QUERIES: dict[str, list[str]] = {
    "dead_vegetation": [
        "dead shrub garden",
        "dry brush yard",
        "dead bush house",
        "brown dried grass lawn",
        "leaf litter garden ground",
    ],
    "overhanging_limbs": [
        "tree branches over roof",
        "tree overhanging house roof",
        "branches touching roof shingles",
        "tree limb above chimney",
    ],
    "veg_touching_structure": [
        "shrub against house wall",
        "vine growing on house wall",
        "bushes against siding",
        "hedge next to house wall",
    ],
    "combustibles_under_deck": [
        "firewood stacked under deck",
        "storage under deck house",
        "clutter under porch",
    ],
    "attached_wood_fence": [
        "wooden fence attached to house",
        "wood gate against house wall",
        "fence meeting house siding",
    ],
    "combustible_mulch_z0": [
        "bark mulch against house foundation",
        "wood chip mulch flower bed house",
        "mulch landscaping next to wall",
    ],
    # Clean yards are training signal too: without them the model invents hazards in a tidy garden.
    "background": [
        "gravel landscaping around house",
        "tidy front yard house",
        "xeriscape front garden",
        "stone landscaping house foundation",
    ],
}


class HarvestError(RuntimeError):
    """A source could not be harvested."""


@dataclass
class HarvestedImage:
    """One candidate image and everything needed to attribute it."""

    filename: str
    source: str
    source_url: str
    licence: str
    licence_url: str
    creator: str
    title: str
    query: str
    # Which class we were looking for. A hint for the auto-labeller, never a label.
    sought_class: str
    width: int | None = None
    height: int | None = None


def _get(url: str, params: dict) -> dict:
    request = urllib.request.Request(  # noqa: S310 - fixed https APIs
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S, context=_SSL) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HarvestError(f"{url}: {exc}") from exc


def search_openverse(query: str, sought_class: str, limit: int) -> list[tuple[str, HarvestedImage]]:
    """Search Openverse. Returns (download_url, metadata) pairs."""
    payload = _get(
        OPENVERSE_API,
        {
            "q": query,
            "page_size": min(limit, 50),
            # Ask the API to filter, then check again ourselves below — a licence field we did not
            # verify is exactly the kind of thing that quietly poisons a published dataset.
            "license": ",".join(sorted(ACCEPTABLE_LICENCES)),
            "mature": "false",
        },
    )

    results = []
    for item in payload.get("results", []):
        licence = (item.get("license") or "").lower()
        url = item.get("url")
        if licence not in ACCEPTABLE_LICENCES or not url:
            continue
        identifier = item.get("id", "")
        results.append(
            (
                url,
                HarvestedImage(
                    filename=f"ov_{identifier}.jpg",
                    source="openverse",
                    source_url=item.get("foreign_landing_url") or url,
                    licence=licence,
                    licence_url=item.get("license_url") or "",
                    creator=item.get("creator") or "unknown",
                    title=item.get("title") or "",
                    query=query,
                    sought_class=sought_class,
                    width=item.get("width"),
                    height=item.get("height"),
                ),
            )
        )
    return results


def search_commons(query: str, sought_class: str, limit: int) -> list[tuple[str, HarvestedImage]]:
    """Search Wikimedia Commons, which is entirely openly licensed."""
    payload = _get(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": min(limit, 50),
            "gsrnamespace": "6",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size",
            "iiurlwidth": "1024",
        },
    )

    results = []
    for page in (payload.get("query", {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        licence = (meta.get("LicenseShortName", {}).get("value") or "").lower()
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        # Commons hosts a few non-free files under exemptions; keep only unambiguous grants.
        if not any(token in licence for token in ("cc0", "public domain", "cc by")):
            continue
        results.append(
            (
                url,
                HarvestedImage(
                    filename=f"wc_{page.get('pageid')}.jpg",
                    source="wikimedia_commons",
                    source_url=info.get("descriptionurl") or url,
                    licence=licence,
                    licence_url=meta.get("LicenseUrl", {}).get("value") or "",
                    creator=(meta.get("Artist", {}).get("value") or "unknown")[:200],
                    title=page.get("title") or "",
                    query=query,
                    sought_class=sought_class,
                    width=info.get("thumbwidth"),
                    height=info.get("thumbheight"),
                ),
            )
        )
    return results


def download(url: str, destination: Path) -> bool:
    """Fetch one image. Returns False rather than raising — one dead link is not a failed run."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S, context=_SSL) as response:
            data = response.read()
    except Exception:  # noqa: BLE001 - any failure here just means we skip this candidate
        return False

    if len(data) < 8_000:
        # Thumbnails and placeholder images are not worth a labelling slot.
        return False
    destination.write_bytes(data)
    return True


def harvest(out_dir: Path, per_query: int = 40, classes: list[str] | None = None) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)

    wanted = classes or list(QUERIES)
    collected: list[HarvestedImage] = []
    seen: set[str] = set()

    for sought_class in wanted:
        for query in QUERIES.get(sought_class, []):
            for search in (search_openverse, search_commons):
                try:
                    candidates = search(query, sought_class, per_query)
                except HarvestError as exc:
                    print(f"  skipped {search.__name__} for {query!r}: {exc}", file=sys.stderr)
                    continue

                for url, meta in candidates:
                    if meta.filename in seen:
                        continue
                    if download(url, out_dir / "images" / meta.filename):
                        seen.add(meta.filename)
                        collected.append(meta)
                time.sleep(PAUSE_BETWEEN_REQUESTS_S)
            print(f"  {sought_class}: {len(collected)} images so far", file=sys.stderr)

    # The attribution file is not optional paperwork — it is what makes publishing the dataset
    # possible, and it is written alongside the images so the two cannot drift apart.
    credits = out_dir / "ATTRIBUTION.json"
    credits.write_text(json.dumps([asdict(image) for image in collected], indent=2) + "\n")

    summary = {
        "images": len(collected),
        "by_class": {
            name: sum(1 for image in collected if image.sought_class == name) for name in wanted
        },
        "by_licence": {
            licence: sum(1 for image in collected if image.licence == licence)
            for licence in sorted({image.licence for image in collected})
        },
        "attribution_file": str(credits),
    }
    (out_dir / "harvest_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("ml/data/harvested"))
    parser.add_argument("--per-query", type=int, default=40)
    parser.add_argument("--class", dest="classes", action="append", choices=sorted(QUERIES))
    args = parser.parse_args()

    summary = harvest(args.out, per_query=args.per_query, classes=args.classes)
    print(json.dumps(summary, indent=2))
    print(
        "\nThese are candidates, not labels. Run `python -m ml.autolabel` next, then review every "
        "box by hand before training."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
