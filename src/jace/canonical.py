from __future__ import annotations

import heapq
from pathlib import Path

from .models import CanonicalEntry
from .model_output import checked_text, source_integrity_reference
from .source_bundle import load_builtin_samples, load_corpus_snapshot
from .text import lexical_terms
from .retrieval_limits import ScanBudget, query_terms, result_limit


class CanonicalStore:
    """Read-only canonical principle store.

    The file is loaded at startup and never mutated through this class.
    Replace it with Neo4j/Kùzu retrieval behind the same interface later.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        package_path = Path(__file__).resolve().parent / "data" / "canonical.json"
        # Empty string is the existing explicit sample-only override used by
        # offline evaluation to ignore a configured external corpus.
        external = path is not None and path != ''
        self.path = Path(path) if external else package_path
        raw, source_bound = load_corpus_snapshot(self.path) if external else (load_builtin_samples(), False)
        if not isinstance(raw, list) or not 1 <= len(raw) <= 256:
            raise ValueError('Canonical corpus must contain 1 through 256 bounded records')
        entries = []
        ordinary = {'entry_id', 'title', 'principle', 'guidance', 'source', 'tags', 'work', 'language', 'edition', 'location', 'license', 'verified'}
        integrity = {'source_sha256', 'source_byte_start', 'source_byte_end'}
        required = {'entry_id', 'title', 'principle', 'guidance', 'source'}
        for item in raw:
            if not isinstance(item, dict) or not required <= set(item) or set(item) - (ordinary | (integrity if source_bound else set())):
                raise ValueError('Canonical records have missing, unknown or unbound integrity fields')
            if source_bound and not integrity <= set(item):
                raise ValueError('Bound source records require complete derived integrity fields')
            for key, maximum in (('entry_id', 128), ('title', 512), ('principle', 20000), ('guidance', 5000), ('source', 1000)):
                checked_text(item[key], 'canonical ' + key, maximum, allow_crlf=key == 'principle')
            if any(c in item['entry_id'] for c in '[]\n\r\t'):
                raise ValueError('Canonical IDs cannot contain citation delimiters or line controls')
            if type(item.get('verified', False)) is not bool:
                raise ValueError('verified must be a boolean declaration')
            for key in ('work', 'language', 'edition', 'location', 'license'):
                if item.get(key) is not None:
                    checked_text(item[key], 'canonical ' + key, 1000)
            tags = item.get('tags', [])
            if not isinstance(tags, list) or len(tags) > 32:
                raise ValueError('canonical tags must be a list of at most 32 text values')
            for tag in tags:
                checked_text(tag, 'canonical tag', 64)
            if external and (item.get('verified') is not True or any(
                not isinstance(item.get(key), str) or not item[key].strip()
                for key in ('work', 'source', 'language', 'location', 'license')
            )):
                raise ValueError('External canonical records require review and work/source/language/location/license declarations')
            entry = CanonicalEntry(**item)
            source_integrity_reference(entry)
            entries.append(entry)
        self._entries = tuple(entries)
        ids = [entry.entry_id for entry in entries]
        if len(set(ids)) != len(ids):
            raise ValueError('Canonical entry IDs must be unique')
        self.source_bound = source_bound

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
