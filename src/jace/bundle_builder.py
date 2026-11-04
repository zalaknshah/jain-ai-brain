"""Build exact-byte source bundles only from explicitly supplied reviewed text."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .source_bundle import (MAX_RECORDS, MAX_SOURCES, MAX_TOTAL_SOURCE_BYTES,
                            read_source_file, write_source_bundle)
from .model_output import checked_text


def _spans(text: str, size: int, overlap: int):
    if type(size) is not int or not 1 <= size <= 1000 or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError('chunk words must be 1 through 1000 and overlap must be smaller')
    words = iter(re.finditer(r'\S+', text))
    buffer = []
    while True:
        added = 0
        while len(buffer) < size:
            match = next(words, None)
            if match is None:
                break
            buffer.append((match.start(), match.end())); added += 1
        if not added:
            return
        yield buffer[0][0], buffer[-1][1]
        if len(buffer) < size:
            return
        buffer = buffer[-overlap:] if overlap else []


def build_exact_bundle(paths, output_directory, *, work: str, source: str, language: str,
                       license_name: str, location: str, verified: bool = False,
                       confirm_build: bool = False, edition: str | None = None,
                       tags: list[str] | None = None, chunk_words: int = 220,
                       overlap_words: int = 40) -> Path:
    if confirm_build is not True or verified is not True:
        raise ValueError('explicit confirmation and human review declaration are required; declarations do not establish source rights or accuracy')
    for name, value in (('work', work), ('source', source), ('language', language), ('license', license_name), ('location', location)):
        checked_text(value, name, 1000)
    # Validate segmentation options before reading any input.
    list(_spans('', chunk_words, overlap_words))
    supplied = []
    for path in paths:
        supplied.append(Path(path))
        if len(supplied) > MAX_SOURCES:
            raise ValueError('too many source files')
    if not supplied:
        raise ValueError('at least one source file is required')
    sources, records, total = {}, [], 0
    for path in supplied:
        if path.suffix.lower() not in ('.txt', '.md', '.markdown'):
            raise ValueError('only explicitly supplied UTF-8 text or Markdown files are supported')
        raw = read_source_file(path)
        total += len(raw)
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('aggregate source byte budget exceeded')
        digest = hashlib.sha256(raw).hexdigest()
        if digest in sources:
            raise ValueError('duplicate source bytes; include each exact source only once')
        sources[digest] = raw
        try:
            text = raw.decode('utf-8')
        except UnicodeError as error:
            raise ValueError('source must be strict UTF-8') from error
        previous_start, previous_byte = 0, 0
        for number, (start, end) in enumerate(_spans(text, chunk_words, overlap_words), 1):
            byte_start = previous_byte + len(text[previous_start:start].encode('utf-8'))
            byte_end = byte_start + len(text[start:end].encode('utf-8'))
            previous_start, previous_byte = start, byte_start
            records.append({'entry_id': f'src:{digest}:{byte_start}:{byte_end}',
                'title': f'{work[:450]} §{number}',
                'guidance': 'Exact source excerpt for contextual analysis; any interpretation must be clearly labelled.',
                'source': source, 'tags': [] if tags is None else tags, 'work': work,
                'language': language, 'edition': edition, 'location': location,
                'license': license_name, 'verified': True,
                'source_ref': {'sha256': digest, 'start': byte_start, 'end': byte_end}})
            if len(records) > MAX_RECORDS:
                raise ValueError('source record count exceeds the bundle limit; no partial output is published')
    return write_source_bundle(output_directory, sources, records)
