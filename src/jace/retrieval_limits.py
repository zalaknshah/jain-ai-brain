"""Fail-closed lexical retrieval work budgets, not a process memory/time sandbox."""
from dataclasses import dataclass
from .text import lexical_terms

MAX_QUERY_CHARS = 10_000
MAX_QUERY_TERMS = 256
MAX_SCAN_ROWS = 10_000
MAX_SCAN_BYTES = 16 * 1024 * 1024
MAX_RECORD_CHARS = 32_768
MAX_RESULTS = 100
MAX_EDGE_ROWS = 50_000


def query_terms(query: str) -> set[str]:
    if not isinstance(query, str) or len(query) > MAX_QUERY_CHARS:
        raise ValueError('retrieval query must be text of at most 10,000 characters')
    result = lexical_terms(query)
    if len(result) > MAX_QUERY_TERMS:
        raise ValueError('retrieval query exceeds the 256 distinct lexical term budget')
    return result


def result_limit(limit: int) -> int:
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError('retrieval result limit must be an integer from 1 through 100')
    return limit


@dataclass
class ScanBudget:
    rows: int = 0
    bytes: int = 0

    def include(self, *texts: str) -> None:
        self.rows += 1
        if self.rows > MAX_SCAN_ROWS:
            raise ValueError('retrieval candidate row budget exceeded; no partial context returned')
        for text in texts:
            if not isinstance(text, str) or len(text) > MAX_RECORD_CHARS:
                raise ValueError('retrieval record exceeds the text size budget')
            self.bytes += len(text.encode('utf-8'))
        if self.bytes > MAX_SCAN_BYTES:
            raise ValueError('retrieval candidate byte budget exceeded; no partial context returned')
