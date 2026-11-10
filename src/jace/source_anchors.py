"""Bounded, in-memory source navigation candidates from existing page OCR.

No files, PDF parser, network, model, source corrections or admission. Matching
two OCR streams cannot independently validate a scan or a complete page boundary.
"""
from __future__ import annotations

import hashlib
import re

MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_WORDS = 200_000
MAX_PAGES = 1000
MAX_PAGE_CHARACTERS = 20_000
MAX_PAGE_TEXT_BYTES = 2 * 1024 * 1024

LIMITATIONS = (
    'Each candidate is an interior span bounded by unique exact OCR anchors, not a complete page or certified citation.',
    'Whitespace is ignored for token matching only. Case, punctuation, spelling and Unicode composition are not changed.',
    'OCR streams may share the same errors; agreement is not independent scan validation or scholarly review.',
    'Headers, footnotes and main text may remain mixed. Unmatched words and surrounding context are not inferred.',
    'Unresolved, reordered and conflicting candidates are reported rather than silently assigned.',
    'This helper grants no rights, runtime, training or source-quality admission and performs no IO.',
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def find_source_anchors(source_bytes: bytes, page_texts: list[str], *, anchor_words: int = 8) -> dict:
    """Return text-free, hash-bound interior spans for already supplied OCR pages.

    The caller supplies extracted pages in page order. This function does not
    verify that extraction against a PDF, authenticate a source or grant consent
    to acquire or use it. Original source bytes are never rewritten. Bounds limit
    this computation's inputs, not the caller or whole-process resources.
    """
    if type(source_bytes) is not bytes or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES:
        raise ValueError('source_bytes must contain 1 through 1048576 bytes')
    if type(anchor_words) is not int or not 4 <= anchor_words <= 16:
        raise ValueError('anchor_words must be an integer from 4 through 16')
    if type(page_texts) is not list or not 1 <= len(page_texts) <= MAX_PAGES:
        raise ValueError('page_texts must be a list of 1 through 1000 extracted page strings')
    total = 0
    for page in page_texts:
        if type(page) is not str or len(page) > MAX_PAGE_CHARACTERS:
            raise ValueError('each page must be a string of at most 20000 characters')
        try:
            total += len(page.encode('utf-8', errors='strict'))
        except UnicodeError as error:
            raise ValueError('page text must be valid UTF-8') from error
        if total > MAX_PAGE_TEXT_BYTES:
            raise ValueError('combined page text exceeds the 2 MiB budget')
    try:
        source = source_bytes.decode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('source_bytes must be valid UTF-8') from error
    words, starts, ends = [], [], []
    previous_character = previous_byte = 0
    for match in re.finditer(r'\S+', source):
        if len(words) == MAX_SOURCE_WORDS:
            raise ValueError('source exceeds the 200000 word budget')
        start = previous_byte + len(source[previous_character:match.start()].encode('utf-8'))
        end = start + len(match.group().encode('utf-8'))
        words.append(match.group()); starts.append(start); ends.append(end)
        previous_character, previous_byte = match.end(), end
    index = {}
    for position in range(len(words) - anchor_words + 1):
        key = tuple(words[position:position + anchor_words])
        index[key] = position if key not in index else None
    pages = []
    for number, text in enumerate(page_texts, 1):
        page_words = text.split()
        matches = []
        for position in range(len(page_words) - anchor_words + 1):
            source_position = index.get(tuple(page_words[position:position + anchor_words]))
            if source_position is not None:
                matches.append((position, source_position))
        item = {'page_ordinal': number, 'page_text_sha256': _digest(text.encode('utf-8')),
                'page_ocr_words': len(page_words), 'unique_exact_anchor_matches': len(matches),
                'status': 'unresolved', 'runtime_admitted': False, 'training_admitted': False,
                'scan_accuracy_reviewed': False, 'source_layers_separated': False}
        if not page_words:
            item['status'] = 'empty_page_text'
        elif len(matches) >= 2:
            first, last = matches[0], matches[-1]
            monotonic = all(b[1] > a[1] for a, b in zip(matches, matches[1:]))
            if (monotonic and last[0] >= first[0] + anchor_words
                    and last[1] >= first[1] + anchor_words
                    and last[1] + anchor_words - first[1] <= 2 * len(page_words)):
                start, end = starts[first[1]], ends[last[1] + anchor_words - 1]
                anchors = []
                for name, (page_position, source_position) in (('first', first), ('last', last)):
                    a, b = starts[source_position], ends[source_position + anchor_words - 1]
                    anchors.append({'kind': name, 'page_word_start': page_position,
                                    'source_byte_start': a, 'source_byte_end': b,
                                    'source_span_sha256': _digest(source_bytes[a:b])})
                matched = set()
                for page_position, _ in matches:
                    matched.update(range(page_position, page_position + anchor_words))
                item.update(status='interior_span_candidate', source_byte_start=start, source_byte_end=end,
                            source_span_sha256=_digest(source_bytes[start:end]), anchors=anchors,
                            exact_matched_page_ocr_words=len(matched))
        pages.append(item)
    candidates = [page for page in pages if page['status'] == 'interior_span_candidate']
    # Check all earlier candidates, including those already marked conflicting.
    # An intervening rejected/reordered page must not hide a longer-range overlap.
    for position, page in enumerate(candidates):
        for earlier in candidates[:position]:
            if page['source_byte_start'] < earlier['source_byte_end']:
                page['status'] = earlier['status'] = 'conflicting_page_candidate'
    return {'schema_version': 1, 'mode': 'source_anchor_candidates',
            'source_sha256': _digest(source_bytes), 'source_byte_length': len(source_bytes),
            'source_words': len(words), 'anchor_words': anchor_words, 'page_count': len(pages),
            'counts': {status: sum(page['status'] == status for page in pages) for status in (
                'interior_span_candidate', 'empty_page_text', 'unresolved', 'conflicting_page_candidate')},
            'pages': pages, 'source_text_included': False, 'source_bytes_changed': False,
            'runtime_admitted': False, 'training_admitted': False, 'limits': list(LIMITATIONS)}
