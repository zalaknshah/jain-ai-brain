from __future__ import annotations

import json
import heapq
from pathlib import Path

from .models import CanonicalEntry
from .text import lexical_terms
from .retrieval_limits import ScanBudget, query_terms, result_limit


class CanonicalStore:
    """Read-only canonical principle store.

    The file is loaded at startup and never mutated through this class.
    Replace it with Neo4j/Kùzu retrieval behind the same interface later.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[2]
        package_path = Path(__file__).resolve().parent / "data" / "canonical.json"
        self.path = Path(path) if path else (root / "data" / "canonical.json" if (root / "data" / "canonical.json").exists() else package_path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not raw:
            raise ValueError("Canonical corpus must be a nonempty list")
        if path:
            for item in raw:
                if not isinstance(item, dict) or item.get("verified") is not True or any(
                    not isinstance(item.get(field), str) or not item[field].strip()
                    for field in ("work", "source", "language", "location", "license")
                ):
                    raise ValueError("External canonical records require human review, work, source, language, location and license metadata")
        # The built-in fallback is explicitly a sample principles file, not a
        # reviewed Agama corpus. External runtime data has stronger admission.
        self._entries = tuple(CanonicalEntry(**item) for item in raw)
        ids = [entry.entry_id for entry in self._entries]
        if any(not isinstance(item, str) or not item.strip() for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("Canonical entry IDs must be nonempty unique strings")

    def all(self) -> list[CanonicalEntry]:
        return list(self._entries)

    def search(self, query: str, limit: int = 5) -> list[CanonicalEntry]:
        terms = query_terms(query)
        limit = result_limit(limit)
        if not terms:
            return []
        budget = ScanBudget()
        def candidates():
            for entry in self._entries:
                fields = list(filter(None, [entry.title, entry.principle, entry.guidance, entry.source,
                              entry.work, entry.edition, entry.location, *entry.tags]))
                budget.include(*fields)
                score = len(terms & lexical_terms(" ".join(fields)))
                if score:
                    yield score, entry.entry_id, entry
        # Lower ID is the existing stable tie-breaker, with O(k) retained rows.
        return [item[2] for item in heapq.nsmallest(limit, candidates(), key=lambda item: (-item[0], item[1]))]
