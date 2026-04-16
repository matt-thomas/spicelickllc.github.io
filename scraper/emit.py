"""Format resolved stocking records as the app-facing JSON feed.

Output shape is fixed by the iOS decoder (see plan + StockingEvent model).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from parsers.sheet import ParsedEvent
from resolve import ResolvedLocation, Resolver


def build_feed(events: list[ParsedEvent], resolver: Resolver, source: str) -> tuple[dict, dict]:
    """Return (stockings_payload, warnings_payload)."""
    feed_events: list[dict] = []
    unresolved_counter: Counter[str] = Counter()
    unresolved_first_seen: dict[str, str] = {}

    for event in events:
        resolved_locations: list[ResolvedLocation] = []
        for loc in event.locations:
            resolved_locations.extend(resolver.resolve(loc))

        feed_locations: list[dict] = []
        for r in resolved_locations:
            feed_locations.append({"id": r.id, "name": r.name, "type": r.type})
            if r.id is None:
                key = r.name.strip()
                unresolved_counter[key] += 1
                unresolved_first_seen.setdefault(key, event.date.isoformat())

        feed_events.append({"date": event.date.isoformat(), "locations": feed_locations})

    feed_events.sort(key=lambda e: e["date"], reverse=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    stockings_payload = {
        "generated_at": now,
        "source": source,
        "events": feed_events,
    }

    unresolved_entries = [
        {
            "raw_name": name,
            "first_seen": unresolved_first_seen[name],
            "occurrences": count,
        }
        for name, count in sorted(unresolved_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    warnings_payload = {"generated_at": now, "unresolved": unresolved_entries}

    return stockings_payload, warnings_payload


def write_payloads(stockings: dict, warnings: dict, out_dir: Path) -> dict[str, bool]:
    """Write the feed files. Returns per-file 'wrote' status so the caller
    can log truthfully."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "stockings.json": _write_if_content_changed(out_dir / "stockings.json", stockings),
        "warnings.json": _write_if_content_changed(out_dir / "warnings.json", warnings),
    }


def _write_if_content_changed(path: Path, payload: dict) -> bool:
    """Write only when the non-timestamp content actually differs. Returns
    True when the file was written, False when skipped. Skipping timestamp-only
    diffs keeps the GitHub Actions cron from opening a PR on every tick — the
    diff gate in the workflow relies on byte equality.
    """
    new_fingerprint = {k: v for k, v in payload.items() if k != "generated_at"}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
            existing_fingerprint = {k: v for k, v in existing.items() if k != "generated_at"}
            if existing_fingerprint == new_fingerprint:
                return False
        except (json.JSONDecodeError, OSError):
            pass
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return True
