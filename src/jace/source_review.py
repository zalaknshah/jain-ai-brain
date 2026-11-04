"""Private, offline source review with separately confirmed local export.

Drafts cannot be loaded as runtime corpora. Review decisions bind the displayed
metadata, exact passages, and complete backing-file digests. These are integrity
checks, not authentication of reviewers, rights, editions or scholarship.
Export retains WHOLE original files, including bytes outside approved spans.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from . import source_bundle as sb
from .bundle_builder import _spans
from .model_output import checked_text

FORMAT = sb.REVIEW_FORMAT
DECISIONS_FORMAT = 'jace-source-decisions-v1'
MAX_DECISIONS_BYTES = 2 * 1024 * 1024
WHOLE_FILE_WARNING = (
    'WARNING: Export copies WHOLE original backing files referenced by approved records. '
    'Those files may contain unapproved text, including rejected, pending or unreviewed text outside approved spans. '
    'Only the runtime records are filtered; backing-file contents are NOT filtered.'
)
_LIMITS = (
    WHOLE_FILE_WARNING,
    'Review-only draft: cannot run as a runtime corpus. No automatic activation, sharing or training.',
    'Source digests and exact byte spans establish local byte identity, not authenticity or scholarly accuracy.',
    'Reviewer identity and qualifications are not authenticated; review and local-retrieval rights are operator declarations, not verified facts.',
    'Review notes are retained only in the separate decision report, not added to the runtime bundle.',
)


def _revision(domain: str, value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(domain.encode('ascii') + b'\0' + raw).hexdigest()


def _snapshot(loaded: list[dict], sources: Mapping[str, bytes], declared: list[dict]) -> dict:
    source_list = [{'sha256': digest, 'byte_length': len(sources[digest])} for digest in sorted(sources)]
    records = [{'entry': entry, 'revision': _revision('jace-source-record-v1',
                {'entry': entry, 'declaration': declaration})}
               for entry, declaration in zip(loaded, declared)]
    revision = _revision('jace-source-draft-v1', {'format': FORMAT, 'sources': source_list, 'records': records})
    return {'protocol': 1, 'kind': 'review_only', 'draft_revision': revision,
            'sources': source_list, 'records': records, 'limits': list(_LIMITS)}


@dataclass(frozen=True)
class _ReviewSnapshot:
    public: dict
    sources: Mapping[str, bytes]
    records: tuple[dict, ...]


def _read_review_snapshot(manifest_path: str | os.PathLike) -> _ReviewSnapshot:
    sb._require_safe_io()
    absolute, components = sb._parts(manifest_path)
    try:
        with sb._DirectoryChain(absolute, components[:-1]) as chain:
            root = chain.fd
            raw = sb._read_regular(root, components[-1], sb.MAX_MANIFEST_BYTES, chain)
            try:
                manifest = sb._json(raw.decode('utf-8', errors='strict'))
            except (UnicodeError, ValueError) as error:
                raise ValueError('invalid UTF-8 source review JSON') from error
            declarations = sb._declarations(manifest, expected_format=FORMAT)
            source_fd = chain.descend(root, 'sources')
            sb._check_source_names(source_fd, set(declarations.values()))
            sources = {}
            total = 0
            for digest, filename in declarations.items():
                data = sb._read_regular(source_fd, filename,
                    min(sb.MAX_SOURCE_BYTES, sb.MAX_TOTAL_SOURCE_BYTES - total), chain)
                total += len(data)
                sources[digest] = data
            sb._validated_sources(sources)
            loaded, normalized = sb._validated_records(manifest['records'], sources, require_review=False)
            public = _snapshot(loaded, sources, manifest['records'])
            sb._check_source_names(source_fd, set(declarations.values()))
            chain.verify()
            # bytes are immutable and the mapping is read-only. Export uses this
            # validated snapshot, never a second read of live backing files.
            return _ReviewSnapshot(public, MappingProxyType(sources), tuple(normalized))
    except OSError as error:
        raise ValueError('cannot safely read source review files') from error


def load_review_package(manifest_path: str | os.PathLike) -> dict:
    """Return a bounded JSON-safe review snapshot, without local path disclosure.

    The HTML is a presentation only and is not trusted as an export authority.
    Revisions bind displayed fields and parsed record declarations, ignoring only
    JSON key order and serialization whitespace. They are recomputed on load.
    """
    return _read_review_snapshot(manifest_path).public


def _draft_record(digest: str, start: int, end: int, number: int, *, work: str,
                  source: str, language: str, license_name: str, location: str,
                  edition: str | None, tags: list[str] | None) -> dict:
    return {'entry_id': f'src:{digest}:{start}:{end}', 'title': f'{work[:450]} §{number}',
            'guidance': 'Exact source excerpt for contextual analysis; any interpretation must be clearly labelled.',
            'source': source, 'tags': [] if tags is None else tags, 'work': work,
            'language': language, 'edition': edition, 'location': location,
            'license': license_name, 'verified': False,
            'source_ref': {'sha256': digest, 'start': start, 'end': end}}


def prepare_source_review(paths, output_directory: str | os.PathLike, *, work: str,
                          source: str, language: str, license_name: str, location: str,
                          confirm_copy: bool = False, edition: str | None = None,
                          tags: list[str] | None = None, chunk_words: int = 220,
                          overlap_words: int = 40) -> Path:
    """Copy explicitly selected UTF-8 files into a new private review-only draft.

    Requires literal True before any input read or copy. Metadata is supplied by
    the operator and is not yet reviewed. WHOLE source files are copied, not just
    excerpts. No network, runtime activation, training or sharing occurs.
    """
    if confirm_copy is not True:
        raise ValueError('explicit confirm_copy=True is required before reading or copying whole source files')
    sb._require_publication_io()
    metadata = dict(work=work, source=source, language=language, license_name=license_name,
                    location=location, edition=edition, tags=tags)
    # Check all descriptive input and segmentation before reading source files.
    checked_text(work, 'work', 1000)
    sb._metadata(_draft_record('0' * 64, 0, 1, 1, **metadata), require_review=False)
    list(_spans('', chunk_words, overlap_words))
    if isinstance(paths, (str, bytes, os.PathLike)):
        raise ValueError('source paths must be an explicit collection of files')
    supplied = []
    for path in paths:
        supplied.append(Path(path))
        if len(supplied) > sb.MAX_SOURCES:
            raise ValueError('too many source files')
    if not supplied:
        raise ValueError('at least one source file is required')
    for path in supplied:
        if path.suffix.lower() not in ('.txt', '.md', '.markdown'):
            raise ValueError('only explicitly supplied UTF-8 text or Markdown files are supported')
    sources, records, total = {}, [], 0
    for path in supplied:
        raw = sb.read_source_file(path)
        total += len(raw)
        if total > sb.MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('aggregate source byte budget exceeded')
        digest = hashlib.sha256(raw).hexdigest()
        if digest in sources:
            raise ValueError('duplicate source bytes; include each exact source only once')
        sources[digest] = raw
        text = raw.decode('utf-8', errors='strict')
        previous_start, previous_byte = 0, 0
        for number, (start, end) in enumerate(_spans(text, chunk_words, overlap_words), 1):
            byte_start = previous_byte + len(text[previous_start:start].encode('utf-8'))
            byte_end = byte_start + len(text[start:end].encode('utf-8'))
            previous_start, previous_byte = start, byte_start
            records.append(_draft_record(digest, byte_start, byte_end, number, **metadata))
            if len(records) > sb.MAX_RECORDS:
                raise ValueError('source record count exceeds the review limit; no partial output is published')
    sb._validated_sources(sources)
    loaded, normalized = sb._validated_records(records, sources, require_review=False)
    from .review_document import render_review_html
    html = render_review_html(_snapshot(loaded, sources, normalized))
    return sb._write_bundle(output_directory, sources, normalized, expected_format=FORMAT,
                            require_review=False, review_html=html)


def _read_decisions(path: str | os.PathLike):
    sb._require_safe_io()
    absolute, components = sb._parts(path)
    try:
        with sb._DirectoryChain(absolute, components[:-1]) as chain:
            raw = sb._read_regular(chain.fd, components[-1], MAX_DECISIONS_BYTES, chain)
            try:
                result = sb._json(raw.decode('utf-8', errors='strict'))
            except (UnicodeError, ValueError) as error:
                raise ValueError('invalid UTF-8 source decision JSON') from error
            chain.verify()
            return result
    except OSError as error:
        raise ValueError('cannot safely read source decision report') from error


def _decision_text(value, name: str, maximum: int, *, allow_empty: bool = False) -> str:
    if (not isinstance(value, str) or len(value) > maximum
            or (not allow_empty and not value.strip())
            or sb._PASSAGE_CONTROLS.search(value) or '\r' in value.replace('\r\n', '')):
        raise ValueError(f'invalid {name}')
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError(f'invalid {name}') from error
    return value


def _validate_decisions(report, snapshot: dict) -> dict[str, str]:
    if not isinstance(report, dict) or set(report) != {'format', 'draft_revision', 'reviewer', 'decisions'} or report['format'] != DECISIONS_FORMAT:
        raise ValueError('invalid source decision report fields or format')
    if sb._digest(report['draft_revision']) != snapshot['draft_revision']:
        raise ValueError('stale decision report: draft revision does not match')
    _decision_text(report['reviewer'], 'reviewer', 128)
    decisions = report['decisions']
    if not isinstance(decisions, list) or len(decisions) != len(snapshot['records']):
        raise ValueError('decision report must include every draft record exactly once')
    expected = {record['entry']['entry_id']: record['revision'] for record in snapshot['records']}
    result = {}
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != {'entry_id', 'record_revision', 'decision', 'note'}:
            raise ValueError('invalid source decision fields')
        entry_id = _decision_text(decision['entry_id'], 'decision entry ID', 128)
        if entry_id not in expected or entry_id in result:
            raise ValueError('unknown or duplicate source decision ID')
        if sb._digest(decision['record_revision']) != expected[entry_id]:
            raise ValueError('stale decision report: record revision does not match')
        choice = decision['decision']
        if not isinstance(choice, str) or choice not in ('approve', 'reject', 'pending'):
            raise ValueError('invalid source review decision')
        _decision_text(decision['note'], 'decision note', 2000, allow_empty=choice == 'pending')
        result[entry_id] = choice
    return result


def export_reviewed_sources(manifest_path: str | os.PathLike, decisions_path: str | os.PathLike,
                            output_directory: str | os.PathLike, *, confirm_export: bool = False,
                            declare_qualified_review: bool = False,
                            declare_rights_for_local_retrieval: bool = False) -> dict:
    """Export approved records after all three separate literal-True declarations.

    confirm_export acknowledges WHOLE backing files (including unapproved bytes)
    are retained. The rights declaration covers whole-file retention and local
    retrieval. Review and rights are operator attestations, not verified facts.
    Reviewer identity/notes stay in the decision report. No activation or sharing.
    """
    if (confirm_export is not True or declare_qualified_review is not True
            or declare_rights_for_local_retrieval is not True):
        raise ValueError(WHOLE_FILE_WARNING + ' Explicit export confirmation, qualified-review declaration '
                         'and rights-for-local-retrieval declaration must each be True.')
    sb._require_publication_io()
    draft = _read_review_snapshot(manifest_path)
    choices = _validate_decisions(_read_decisions(decisions_path), draft.public)
    approved = [{**record, 'verified': True} for record in draft.records
                if choices[record['entry_id']] == 'approve']
    if not approved:
        raise ValueError('at least one explicitly approved record is required; nothing was exported')
    selected = {record['source_ref']['sha256'] for record in approved}
    sources = {digest: draft.sources[digest] for digest in sorted(selected)}
    path = sb.write_source_bundle(output_directory, sources, approved)
    return {'manifest_path': str(path), 'approved_records': len(approved),
            'rejected_records': sum(choice == 'reject' for choice in choices.values()),
            'pending_records': sum(choice == 'pending' for choice in choices.values()),
            'source_count': len(sources), 'warning': WHOLE_FILE_WARNING}
