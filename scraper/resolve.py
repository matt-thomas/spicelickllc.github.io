"""Resolve raw stocking names to canonical waterbody IDs.

Lookup flow:
  1. Lowercase the raw name.
  2. Consult ``data/aliases.json`` (ported from LocationMatcher.swift).
  3. If no alias, try the cleaned name (raw with type suffixes stripped).
  4. Map the canonical *name* to one or more feature *IDs* via the waterbody
     catalog. Multiple IDs is the normal case for multi-section waterbodies
     (e.g. North Branch Potomac → 3 IDs → 3 emitted locations).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from parsers.sheet import ParsedLocation, clean_name


@dataclass(frozen=True)
class ResolvedLocation:
    id: Optional[str]
    name: str  # resolved geometry name when id is set, raw sheet string otherwise
    type: str


class Resolver:
    def __init__(
        self,
        aliases: dict[str, str],
        name_to_ids: dict[str, list[str]],
        id_to_name: dict[str, str],
    ) -> None:
        self._aliases = aliases
        self._name_to_ids = name_to_ids
        self._id_to_name = id_to_name

    @classmethod
    def from_files(cls, aliases_path: Path, waterbodies_path: Path) -> "Resolver":
        aliases_raw = json.loads(aliases_path.read_text())
        aliases = {k.lower().strip(): v for k, v in aliases_raw.items()}
        catalog = json.loads(waterbodies_path.read_text())
        name_to_ids: dict[str, list[str]] = {}
        id_to_name: dict[str, str] = {}
        for entry in catalog:
            name_to_ids.setdefault(entry["name"], []).append(entry["id"])
            id_to_name[entry["id"]] = entry["name"]
        return cls(aliases, name_to_ids, id_to_name)

    def resolve(self, location: ParsedLocation) -> list[ResolvedLocation]:
        canonical_name = self._lookup_canonical_name(location.raw_name)
        if canonical_name is None:
            return [ResolvedLocation(id=None, name=location.raw_name, type=location.type)]

        ids = self._name_to_ids.get(canonical_name, [])
        if not ids:
            return [ResolvedLocation(id=None, name=location.raw_name, type=location.type)]

        return [
            ResolvedLocation(id=fid, name=self._id_to_name[fid], type=location.type)
            for fid in ids
        ]

    def _lookup_canonical_name(self, raw: str) -> Optional[str]:
        key = raw.lower().strip()
        if key in self._aliases:
            return self._aliases[key]
        cleaned = clean_name(raw).lower().strip()
        if cleaned and cleaned != key and cleaned in self._aliases:
            return self._aliases[cleaned]
        return None
