"""Unit tests for the Google Sheet parser."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

SCRAPER_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRAPER_ROOT))

from parsers.sheet import CATFISH, GOLD_RUSH, TROUT, parse_rows


def _parse(rows, today=date(2026, 4, 16)):
    return parse_rows([["Date", "Location"], *rows], today=today)


class SheetParserTests(unittest.TestCase):
    def test_basic_multiline_cell_with_section_headers(self):
        events = _parse([["4/15/2026", "TROUT STOCKING:\nCherry River\nBlackwater River"]])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].date, date(2026, 4, 15))
        self.assertEqual(
            [loc.raw_name for loc in events[0].locations],
            ["Cherry River", "Blackwater River"],
        )
        self.assertTrue(all(loc.type == TROUT for loc in events[0].locations))

    def test_gold_rush_section_header_applies_to_following_lines(self):
        events = _parse(
            [["4/10/2026", "TROUT STOCKING:\nCherry River\nGOLD RUSH STOCKING:\nBlackwater River"]]
        )
        self.assertEqual(len(events[0].locations), 2)
        self.assertEqual(events[0].locations[0].type, TROUT)
        self.assertEqual(events[0].locations[1].type, GOLD_RUSH)

    def test_inline_prefix_format_is_not_dropped(self):
        """Regression for the bug in GoogleSheetsService.swift:77-103 where a single
        line like ``TROUT STOCKING North River`` was treated as a header-only line,
        silently dropping the waterbody."""
        events = _parse([["6/6/2025", "TROUT STOCKING North River"]])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].locations), 1)
        self.assertEqual(events[0].locations[0].raw_name, "North River")
        self.assertEqual(events[0].locations[0].type, TROUT)

    def test_inline_prefix_catfish_and_plural(self):
        events = _parse([["6/2/2025", "CHANNEL CATFISH STOCKINGS Buffalo Fork Lake"]])
        self.assertEqual(events[0].locations[0].raw_name, "Buffalo Fork Lake")
        self.assertEqual(events[0].locations[0].type, CATFISH)

    def test_no_stocking_and_no_waters_rows_are_dropped(self):
        events = _parse([
            ["4/12/2026", "No stocking"],
            ["4/13/2026", "Holiday"],
            ["4/14/2026", "No waters stocked due to weather."],
            ["4/15/2026", "Cherry River"],
        ])
        self.assertEqual([e.date.day for e in events], [15])

    def test_html_entities_are_decoded(self):
        events = _parse([["4/11/2026", "Elk River (C&amp;R)"]])
        self.assertEqual(events[0].locations[0].raw_name, "Elk River (C&R)")

    def test_curly_apostrophe_is_normalized(self):
        events = _parse([["4/11/2026", "O\u2019Brien Lake"]])
        self.assertEqual(events[0].locations[0].raw_name, "O'Brien Lake")

    def test_per_line_suffix_overrides_default_type(self):
        events = _parse(
            [["4/15/2026", "TROUT STOCKING:\nBlackwater River Gold Rush\nCherry River"]]
        )
        self.assertEqual(events[0].locations[0].type, GOLD_RUSH)
        self.assertEqual(events[0].locations[1].type, TROUT)

    def test_year_window_filters_out_old_rows(self):
        events = _parse(
            [
                ["3/1/2023", "Ancient Creek"],
                ["3/1/2025", "Recent Creek"],
                ["3/1/2026", "Current Creek"],
            ],
            today=date(2026, 4, 16),
        )
        self.assertEqual(
            [loc.raw_name for e in events for loc in e.locations],
            ["Recent Creek", "Current Creek"],
        )


if __name__ == "__main__":
    unittest.main()
