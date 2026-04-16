"""Unit tests for the alias → canonical ID resolver."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRAPER_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRAPER_ROOT))

from parsers.sheet import GOLD_RUSH, TROUT, ParsedLocation
from resolve import Resolver


def _make_resolver(aliases: dict, catalog: list) -> Resolver:
    tmp = Path(tempfile.mkdtemp())
    aliases_path = tmp / "aliases.json"
    catalog_path = tmp / "waterbodies.json"
    aliases_path.write_text(json.dumps(aliases))
    catalog_path.write_text(json.dumps(catalog))
    return Resolver.from_files(aliases_path, catalog_path)


class ResolverTests(unittest.TestCase):
    def test_single_waterbody_resolves_to_one_id(self):
        resolver = _make_resolver(
            {"anthony creek": "Anthony Creek"},
            [{"id": "stream:greenbrier:anthony-creek", "kind": "stream",
              "name": "Anthony Creek", "county": "Greenbrier"}],
        )
        out = resolver.resolve(ParsedLocation(raw_name="Anthony Creek", type=TROUT))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "stream:greenbrier:anthony-creek")
        self.assertEqual(out[0].type, TROUT)

    def test_multi_section_waterbody_fans_out_to_all_ids(self):
        """When a canonical name has multiple sections (like N. Branch Potomac),
        one raw name resolves to one emitted location *per section*."""
        resolver = _make_resolver(
            {"north branch potomac river": "North Branch Potomac River"},
            [
                {"id": "stream:mineral:north-branch-potomac-river-lower", "kind": "stream",
                 "name": "North Branch Potomac River", "county": "Mineral"},
                {"id": "stream:mineral:north-branch-potomac-river-middle", "kind": "stream",
                 "name": "North Branch Potomac River", "county": "Mineral"},
                {"id": "stream:mineral:north-branch-potomac-river-upper", "kind": "stream",
                 "name": "North Branch Potomac River", "county": "Mineral"},
            ],
        )
        out = resolver.resolve(ParsedLocation(raw_name="North Branch Potomac River", type=TROUT))
        self.assertEqual(len(out), 3)
        self.assertEqual(
            {r.id for r in out},
            {
                "stream:mineral:north-branch-potomac-river-lower",
                "stream:mineral:north-branch-potomac-river-middle",
                "stream:mineral:north-branch-potomac-river-upper",
            },
        )
        self.assertTrue(all(r.type == TROUT for r in out))

    def test_alias_with_type_suffix_uses_base_waterbody(self):
        resolver = _make_resolver(
            {"blackwater river gold rush": "Blackwater River"},
            [{"id": "stream:tucker:blackwater-river", "kind": "stream",
              "name": "Blackwater River", "county": "Tucker"}],
        )
        out = resolver.resolve(ParsedLocation(raw_name="Blackwater River Gold Rush", type=GOLD_RUSH))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "stream:tucker:blackwater-river")
        self.assertEqual(out[0].type, GOLD_RUSH)

    def test_unresolvable_name_preserves_raw_name_with_null_id(self):
        resolver = _make_resolver({}, [])
        out = resolver.resolve(ParsedLocation(raw_name="Unknown Water", type=TROUT))
        self.assertEqual(len(out), 1)
        self.assertIsNone(out[0].id)
        self.assertEqual(out[0].raw_name, "Unknown Water")

    def test_cleaned_name_fallback_when_raw_has_type_suffix(self):
        """The alias table may hold the base name; if the raw includes 'Gold Rush'
        but the alias doesn't, resolver falls back to cleaned name."""
        resolver = _make_resolver(
            {"cherry river": "Cherry River"},
            [{"id": "stream:nicholas:cherry-river", "kind": "stream",
              "name": "Cherry River", "county": "Nicholas"}],
        )
        out = resolver.resolve(ParsedLocation(raw_name="Cherry River Gold Rush", type=GOLD_RUSH))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "stream:nicholas:cherry-river")


if __name__ == "__main__":
    unittest.main()
