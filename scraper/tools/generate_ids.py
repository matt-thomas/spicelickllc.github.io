"""Assign canonical IDs to every waterbody in the iOS app's geometry.json.

Pipeline (run from scraper/):

    python3 tools/generate_ids.py \
        --input ../../wv-trout-map/wv-topo-svg/output/geometry.json \
        --output ../../wv-trout-map/WVTroutMap/Resources/geometry.json

Reads an enriched geometry file (produced by wv-topo-svg/fetch_geometry.py),
assigns each feature a stable `id` of the form

    {kind}:{county-slug}:{name-slug}[-section]

and writes:
  - the final bundled geometry.json (with `id` on every feature)
  - scraper/data/waterbodies.json (the canonical ID catalog for the scraper)

Collisions on (kind, county, name) are treated as distinct stocked sections of
the same waterbody (e.g. three segments of the North Branch Potomac River).
Sections are sorted south→north by starting latitude and suffixed -lower /
-middle / -upper (for 2: -lower / -upper; for N>3: -section-N).

Idempotent: running twice produces the same output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRAPER_ROOT = Path(__file__).resolve().parent.parent
WATERBODIES_PATH = SCRAPER_ROOT / "data" / "waterbodies.json"


def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\u2018\u2019'`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def section_suffix(index: int, total: int) -> str:
    if total == 2:
        return ["lower", "upper"][index]
    if total == 3:
        return ["lower", "middle", "upper"][index]
    return f"section-{index + 1}"


def starting_latitude(feature: dict) -> float:
    paths = feature.get("paths") or feature.get("rings") or []
    if not paths or not paths[0]:
        return 0.0
    return paths[0][0][0]


def assign_ids(features: list[dict], kind: str) -> None:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in features:
        groups[(f["name"], f["county"])].append(f)

    for (name, county), records in groups.items():
        base = f"{kind}:{slug(county)}:{slug(name)}"
        if len(records) == 1:
            records[0]["id"] = base
            continue

        records.sort(key=starting_latitude)
        total = len(records)
        for i, record in enumerate(records):
            suffix = section_suffix(i, total)
            record["id"] = f"{base}-{suffix}"
            record["section"] = suffix
        print(
            f"  {name!r} ({county}): {total} sections → "
            f"{', '.join(r['section'] for r in records)}"
        )

    seen: dict[str, dict] = {}
    for f in features:
        if f["id"] in seen:
            raise SystemExit(f"ID collision (bug): {f['id']!r}")
        seen[f["id"]] = f


def build_waterbody_catalog(streams: list[dict], lakes: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for f in streams:
        entry = {"id": f["id"], "kind": "stream", "name": f["name"], "county": f["county"]}
        if "section" in f:
            entry["section"] = f["section"]
        entries.append(entry)
    for f in lakes:
        entry = {"id": f["id"], "kind": "lake", "name": f["name"], "county": f["county"]}
        if "section" in f:
            entry["section"] = f["section"]
        entries.append(entry)
    entries.sort(key=lambda x: x["id"])
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="enriched geometry.json (no IDs)")
    parser.add_argument("--output", type=Path, required=True, help="final bundled geometry.json (with IDs)")
    args = parser.parse_args()

    data = json.loads(args.input.read_text())
    print(f"Input:  {args.input}")
    print(f"  streams: {len(data['streams'])}   lakes: {len(data['lakes'])}")

    print("\nSection splits:")
    assign_ids(data["streams"], "stream")
    assign_ids(data["lakes"], "lake")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(",", ":")))
    print(f"\nWrote {args.output}  ({args.output.stat().st_size / 1024:.1f} KB)")

    WATERBODIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    catalog = build_waterbody_catalog(data["streams"], data["lakes"])
    WATERBODIES_PATH.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Wrote {WATERBODIES_PATH}  ({len(catalog)} entries)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
