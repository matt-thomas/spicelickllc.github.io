"""Parse the WV DNR stocking Google Sheet into structured events.

Ported from WVTroutMap/Services/GoogleSheetsService.swift:77-103, plus a fix for
the inline-prefix format (e.g. "TROUT STOCKING North River" on one line),
which the Swift parser silently drops.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

StockingType = str  # "trout" | "gold_rush" | "catfish"
TROUT: StockingType = "trout"
GOLD_RUSH: StockingType = "gold_rush"
CATFISH: StockingType = "catfish"

_TYPE_SUFFIXES: tuple[tuple[str, StockingType], ...] = (
    ("(gold rush)", GOLD_RUSH),
    (" gold rush", GOLD_RUSH),
    ("(channel catfish)", CATFISH),
    (" channel catfish", CATFISH),
    ("(trout)", TROUT),
)

_SECTION_HEADERS: tuple[tuple[re.Pattern[str], StockingType], ...] = (
    (re.compile(r"\bGOLD RUSH STOCKINGS?\b", re.IGNORECASE), GOLD_RUSH),
    (re.compile(r"\bCHANNEL CATFISH STOCKINGS?\b", re.IGNORECASE), CATFISH),
    (re.compile(r"\bTROUT STOCKINGS?\b", re.IGNORECASE), TROUT),
)

_HEADER_ONLY_LINE = re.compile(
    r"^\s*(?:TROUT|GOLD RUSH|CHANNEL CATFISH)\s+STOCKINGS?\s*:?\s*$",
    re.IGNORECASE,
)

_NON_LOCATION_HEADERS = (
    "STOCKING SCHEDULE",
    "STOCKING UPDATE",
    "WEEKLY STOCKING",
)


@dataclass(frozen=True)
class ParsedLocation:
    raw_name: str
    type: StockingType


@dataclass(frozen=True)
class ParsedEvent:
    date: date
    locations: tuple[ParsedLocation, ...]


def clean_name(name: str) -> str:
    """Strip known type suffixes so the lookup can match on the base name."""
    result = name.strip()
    lowered = result.lower()
    for suffix, _ in _TYPE_SUFFIXES:
        if lowered.endswith(suffix):
            result = result[: -len(suffix)].strip()
            lowered = result.lower()
    return result


def _is_non_location_header(line: str) -> bool:
    upper = line.upper().strip()
    return any(pattern in upper for pattern in _NON_LOCATION_HEADERS)


def _type_from_suffix(name: str, default: StockingType) -> StockingType:
    lowered = name.lower()
    for suffix, stype in _TYPE_SUFFIXES:
        if suffix in lowered:
            return stype
    return default


def _extract_inline_header(line: str) -> tuple[StockingType, str] | tuple[None, None]:
    """Handle ``"TROUT STOCKING North River"`` style lines.

    The existing Swift parser drops these because it treats any line containing
    a section-header phrase as a header-only line. We split the prefix off and
    keep the trailing waterbody name.
    """
    for pattern, stype in _SECTION_HEADERS:
        match = pattern.search(line)
        if not match:
            continue
        remainder = (line[: match.start()] + line[match.end():]).strip(" :,-\t")
        if remainder:
            return stype, remainder
    return None, None


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _year_window_contains(d: date, window_years: int, now: date | None = None) -> bool:
    now = now or date.today()
    earliest_year = now.year - (window_years - 1)
    return earliest_year <= d.year <= now.year


def parse_rows(
    rows: Iterable[list[str]],
    *,
    year_window: int = 2,
    today: date | None = None,
) -> list[ParsedEvent]:
    """Parse Google Sheet rows (skip header row) into structured events."""
    events: list[ParsedEvent] = []
    rows_iter = iter(rows)
    next(rows_iter, None)  # skip header

    for row in rows_iter:
        if len(row) < 2:
            continue
        event_date = _parse_date(row[0])
        if event_date is None or not _year_window_contains(event_date, year_window, today):
            continue

        cell = html.unescape(row[1]).replace("\u2019", "'")
        lines = [ln.strip() for ln in cell.splitlines()]
        lines = [ln for ln in lines if ln]

        if len(lines) == 1:
            only = lines[0].lower()
            if "no stocking" in only or "no waters" in only or "holiday" in only:
                continue

        locations: list[ParsedLocation] = []
        current_type: StockingType = TROUT

        for line in lines:
            if _HEADER_ONLY_LINE.match(line):
                for pattern, stype in _SECTION_HEADERS:
                    if pattern.search(line):
                        current_type = stype
                        break
                continue

            inline_type, inline_name = _extract_inline_header(line)
            if inline_type is not None and inline_name:
                current_type = inline_type
                line = inline_name

            if _is_non_location_header(line):
                continue

            location_type = _type_from_suffix(line, current_type)
            locations.append(ParsedLocation(raw_name=line, type=location_type))

        if locations:
            events.append(ParsedEvent(date=event_date, locations=tuple(locations)))

    return events
