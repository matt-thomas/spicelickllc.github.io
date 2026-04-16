"""Scrape the WV DNR stocking Google Sheet and publish a canonical JSON feed.

The Sheet is the authoritative upstream (the wvdnr.gov fish-stocking page just
renders this same sheet via remote-table.js). We fetch it over the public
Sheets API, parse rows into structured events, resolve names against the
migrated alias table + canonical ID catalog, and write the feed under
``wv-trout/`` in the Pages repo where it's served at
``https://spice-lick.com/wv-trout/stockings.json``.

Required environment variables (both must be set — no defaults):

    SHEET_ID          The Google Sheets document ID
    SHEETS_API_KEY    A Google Sheets API v4 read key for that document

In CI these come from repo secrets. For local runs:

    SHEET_ID=... SHEETS_API_KEY=... python3 scrape.py --out ../wv-trout

Or skip the fetch entirely with a local fixture:

    python3 scrape.py --out /tmp/out --sheet-fixture fixtures/sheet_rows.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from emit import build_feed, write_payloads
from parsers.sheet import parse_rows
from resolve import Resolver

SCRAPER_ROOT = Path(__file__).resolve().parent
DEFAULT_ALIASES = SCRAPER_ROOT / "data" / "aliases.json"
DEFAULT_WATERBODIES = SCRAPER_ROOT / "data" / "waterbodies.json"
DEFAULT_OUT_DIR = SCRAPER_ROOT.parent / "wv-trout"

SHEET_TAB = "Sheet1"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"error: environment variable {name} is required but not set.\n"
            f"       set it via repo secrets (CI) or your shell (local)."
        )
    return value


def fetch_sheet_rows(sheet_id: str, api_key: str) -> list[list[str]]:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
        f"/values/{SHEET_TAB}?key={api_key}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload: dict[str, Any] = json.loads(resp.read())
    return payload.get("values", [])


def load_rows_from_fixture(path: Path) -> list[list[str]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict) and "values" in payload:
        return payload["values"]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Output directory for stockings.json and warnings.json")
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--waterbodies", type=Path, default=DEFAULT_WATERBODIES)
    parser.add_argument("--sheet-fixture", type=Path, help="Load rows from a local JSON fixture instead of fetching.")
    parser.add_argument("--year-window", type=int, default=2, help="Retain events from the last N years (inclusive).")
    parser.add_argument("--today", type=str, help="Override 'today' for deterministic runs (YYYY-MM-DD).")
    args = parser.parse_args()

    if args.sheet_fixture:
        rows = load_rows_from_fixture(args.sheet_fixture)
        source = f"fixture:{args.sheet_fixture.name}"
    else:
        sheet_id = _require_env("SHEET_ID")
        api_key = _require_env("SHEETS_API_KEY")
        rows = fetch_sheet_rows(sheet_id, api_key)
        # Never include the Sheet ID in the published feed — it's a secret.
        source = "google-sheet"

    today = date.fromisoformat(args.today) if args.today else None
    events = parse_rows(rows, year_window=args.year_window, today=today)
    print(f"Parsed {len(events)} events from {len(rows)} sheet rows")

    resolver = Resolver.from_files(args.aliases, args.waterbodies)
    stockings, warnings = build_feed(events, resolver, source)

    wrote = write_payloads(stockings, warnings, args.out)
    stockings_tag = "wrote" if wrote["stockings.json"] else "unchanged"
    warnings_tag = "wrote" if wrote["warnings.json"] else "unchanged"
    print(f"{stockings_tag}: {args.out / 'stockings.json'}  ({len(stockings['events'])} events)")
    print(f"{warnings_tag}: {args.out / 'warnings.json'}  ({len(warnings['unresolved'])} unresolved names)")

    if warnings["unresolved"]:
        top = warnings["unresolved"][:5]
        print("\nTop unresolved names:")
        for entry in top:
            print(f"  {entry['occurrences']:3}×  {entry['raw_name']!r}  (first seen {entry['first_seen']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
