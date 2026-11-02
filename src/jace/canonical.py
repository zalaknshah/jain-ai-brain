from __future__ import annotations

import json
import re
from pathlib import Path

from .models import CanonicalEntry


class CanonicalStore:
    """Read-only canonical principle store.

    The file is loaded at startup and never mutated through this class.
    Replace it with Neo4j/Kùzu retrieval behind the same interface later.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.path = Path(path) if path else root / "data" / "canonical.json"
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._entries = tuple(CanonicalEntry(**item) for item in raw)

    def all(self) -> list[CanonicalEntry]:
        return list(self._entries)

    def search(self, query: str, limit: int = 5) -> list[CanonicalEntry]:
        terms = set(re.findall(r"[\w-]+", query.lower()))
        if not terms:
            return []

        def score(entry: CanonicalEntry) -> int:
            haystack = " ".join([entry.title, entry.principle, entry.guidance, *entry.tags]).lower()
            return sum(1 for term in terms if term in haystack)

        ranked = sorted(self._entries, key=lambda item: (-score(item), item.entry_id))
        return [entry for entry in ranked if score(entry) > 0][:limit]
