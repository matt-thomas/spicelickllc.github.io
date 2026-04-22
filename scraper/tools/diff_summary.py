"""Print a short human-readable summary of the diff between the committed
wv-trout/stockings.json and the current working-tree version. Used by the
scrape workflow to fill in the PR body.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FEED_PATH = REPO_ROOT / "wv-trout" / "stockings.json"
WARNINGS_PATH = REPO_ROOT / "wv-trout" / "warnings.json"


def _load_committed_feed() -> dict | None:
    try:
        out = subprocess.run(
            ["git", "show", "HEAD:wv-trout/stockings.json"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    return json.loads(out.stdout)


def _locations_by_date(feed: dict) -> dict[str, list[tuple]]:
    result: dict[str, list[tuple]] = {}
    for event in feed.get("events", []):
        locs = tuple(
            (l.get("id") or l.get("raw_name"), l.get("type")) for l in event["locations"]
        )
        result[event["date"]] = sorted(locs, key=lambda t: (t[0] or "", t[1] or ""))
    return result


def main() -> int:
    current = json.loads(FEED_PATH.read_text())
    committed = _load_committed_feed()

    cur_map = _locations_by_date(current)
    old_map = _locations_by_date(committed) if committed else {}

    added_dates = sorted(set(cur_map) - set(old_map))
    removed_dates = sorted(set(old_map) - set(cur_map))
    changed_dates = sorted(d for d in cur_map.keys() & old_map.keys() if cur_map[d] != old_map[d])

    cur_locs = sum(len(e["locations"]) for e in current["events"])
    old_locs = sum(len(e["locations"]) for e in committed["events"]) if committed else 0

    warnings = json.loads(WARNINGS_PATH.read_text()) if WARNINGS_PATH.exists() else {"unresolved": []}

    lines: list[str] = []
    lines.append(f"**Events:** {len(cur_map)} total (+{len(added_dates)} / -{len(removed_dates)} / ~{len(changed_dates)})")
    lines.append(f"**Locations:** {cur_locs} total ({cur_locs - old_locs:+d})")

    def _fmt_dates(dates: list[str], limit: int = 8) -> str:
        if not dates:
            return "_none_"
        shown = dates[:limit]
        suffix = f" _(+{len(dates) - limit} more)_" if len(dates) > limit else ""
        return ", ".join(shown) + suffix

    if added_dates:
        lines.append(f"**Added dates:** {_fmt_dates(added_dates)}")
    if changed_dates:
        lines.append(f"**Updated dates:** {_fmt_dates(changed_dates)}")
    if removed_dates:
        lines.append(f"**Removed dates:** {_fmt_dates(removed_dates)}")

    if warnings["unresolved"]:
        top = warnings["unresolved"][:5]
        lines.append("")
        lines.append(f"⚠️ **{len(warnings['unresolved'])} unresolved name(s)** — review and add to `scraper/data/aliases.json` if they map to real waterbodies:")
        for entry in top:
            lines.append(f"- `{entry['raw_name']}` × {entry['occurrences']} (first {entry['first_seen']})")
    else:
        lines.append("")
        lines.append("✅ 0 unresolved names.")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
