"""Local-only, read-only, explicit per-invocation source-study API. No CLI."""
from dataclasses import dataclass
import json
import os
import re
import stat
from . import preparation as fresh

CONSUMER_VERSION = 'jace-fresh-private-consumer-v1'
PURPOSE = 'fresh-private-source-study'
MAX_CONTEXT = 8
LIMITS = {
    'original.xml': fresh.MAX_SOURCE_BYTES,
    'ATTRIBUTION.md': fresh.MAX_NOTICE_BYTES,
    'accession.json': fresh.MAX_NOTICE_BYTES,
    'CHANGES.txt': fresh.MAX_NOTICE_BYTES,
    'records.jsonl': fresh.MAX_OUTPUT_BYTES,
    'manifest.json': fresh.MAX_NOTICE_BYTES,
}

class ConsumerError(ValueError):
    """Fail closed, with no source body or local path in the diagnostic."""

@dataclass(frozen=True)
class ExpectedPins:
    source_sha256: str
    attribution_sha256: str
    accession_sha256: str
    changes_sha256: str
    records_sha256: str
    manifest_sha256: str

@dataclass(frozen=True)
class StudyDeclaration:
    consumer_version: str
    preparation_version: str
    source_sha256: str
    accepted_license: str
    purpose: str
    opted_in: bool


def _signature(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns, st.st_uid, st.st_gid)


class _Snapshot:
    """Keep every directory and file descriptor open through verification."""
    def __init__(self, path):
        self.entries = []
        self.path = path

    def _open(self, name, parent, directory, private=False):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        fd = os.open(name, flags, dir_fd=parent)
        st = os.fstat(fd)
        self.entries.append((fd, parent, name, _signature(st)))
        if directory:
            if not stat.S_ISDIR(st.st_mode):
                raise ConsumerError('A directory component is not a directory')
        elif not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise ConsumerError('Bundle files must be regular and singly linked')
        if private and (st.st_uid != os.geteuid() or st.st_mode & 0o077):
            raise ConsumerError('Bundle directory and files require private ownership and modes')
        return fd

    def __enter__(self):
        try:
            # Reject lexical aliases rather than resolve symlinks implicitly.
            if type(self.path) is not str or not self.path.startswith('/'):
                raise ConsumerError('An explicit absolute bundle directory is required')
            parts = self.path.split('/')[1:]
            if not parts or any(p in ('', '.', '..') or '\x00' in p for p in parts):
                raise ConsumerError('Invalid bundle directory components')
            root = self._open('/', None, True)
            for i, part in enumerate(parts):
                root = self._open(part, root, True, private=(i == len(parts)-1))
            raw = {}
            for name, limit in LIMITS.items():
                fd = self._open(name, root, False, private=True)
                size = os.fstat(fd).st_size
                if size <= 0 or size > limit:
                    raise ConsumerError('Bundle file exceeds bounded input limits')
                chunks, total = [], 0
                while True:
                    chunk = os.read(fd, min(65536, limit + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ConsumerError('Bundle file exceeds bounded input limits')
                    chunks.append(chunk)
                raw[name] = b''.join(chunks)
                if total != size:
                    raise ConsumerError('Bundle file changed during read')
            self.check()
            return self, raw
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self):
        for fd, parent, name, signature in self.entries:
            if (_signature(os.fstat(fd)) != signature or
                    _signature(os.stat(name, dir_fd=parent, follow_symlinks=False)) != signature):
                raise ConsumerError('Bundle or directory changed during invocation')

    def __exit__(self, *unused):
        for fd, _, _, _ in reversed(self.entries):
            os.close(fd)
        self.entries.clear()


def _validate(pins, declaration):
    if type(pins) is not ExpectedPins:
        raise ConsumerError('Independently supplied expected pins are required')
    if any(type(v) is not str or not re.fullmatch('[0-9a-f]{64}', v)
           for v in vars(pins).values()):
        raise ConsumerError('Invalid expected fingerprint')
    if (type(declaration) is not StudyDeclaration or declaration.opted_in is not True or
            declaration.consumer_version != CONSUMER_VERSION or
            declaration.preparation_version != fresh.FORMAT or
            declaration.source_sha256 != pins.source_sha256 or
            declaration.accepted_license != fresh.LICENSE or declaration.purpose != PURPOSE):
        raise ConsumerError('Exact version, source, license and private purpose opt-in required')


def consume(bundle_directory, *, pins, declaration, operation='inventory',
            xml_id=None, before=0, after=0, reviewed_noncandidates=False,
            query=None, limit=None, offset=None, xml_ids=None):
    """Verify the complete bundle each call; return separate records, never an answer.

    Inventory contains aggregate metadata only. Lookup matches one exact selected
    unit's xml:id; context counts adjacent extracted records (including overlaps),
    not verses or sentences. Noncandidate windows require separate literal True.
    No caller pin is derived from the bundle. No files are written or logged.
    """
    _validate(pins, declaration)
    if type(reviewed_noncandidates) is not bool:
        raise ConsumerError('Review opt-in must be a boolean')
    if (type(before) is not int or type(after) is not int or
            not 0 <= before <= MAX_CONTEXT or not 0 <= after <= MAX_CONTEXT):
        raise ConsumerError('Context bounds must be integers from zero through eight')
    if operation not in ('inventory', 'lookup', 'search', 'browse', 'select'):
        raise ConsumerError('Unsupported operation')
    if operation == 'select':
        if (type(xml_ids) is not list or not 2 <= len(xml_ids) <= 5 or
                any(type(x) is not str or not x or len(x) > 256 for x in xml_ids) or
                len(set(xml_ids)) != len(xml_ids) or xml_id is not None or before or after):
            raise ConsumerError('Select requires two through five distinct exact XML IDs')
    elif xml_ids is not None:
        raise ConsumerError('Multiple XML IDs require select operation')
    if operation == 'inventory' and (xml_id is not None or before or after or reviewed_noncandidates):
        raise ConsumerError('Inventory does not accept lookup or disclosure options')
    if operation == 'lookup' and (type(xml_id) is not str or not xml_id or len(xml_id) > 256):
        raise ConsumerError('An exact bounded XML ID is required')
    if operation not in ('search', 'browse') and (query is not None or limit is not None or offset is not None):
        raise ConsumerError('Search options require the search operation')
    if operation == 'search':
        if (xml_id is not None or before or after or type(query) is not str or
                not 1 <= len(query) <= 128 or not query.strip() or
                any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in query) or
                type(limit) is not int or not 1 <= limit <= 8):
            raise ConsumerError('Search requires a bounded literal query and integer limit one through eight')
    if operation == 'browse' and (xml_id is not None or before or after or query is not None or
            type(limit) is not int or not 1 <= limit <= 8 or offset is None):
        raise ConsumerError('Browse requires explicit offset and limit without lookup/search options')
    if operation in ('search', 'browse'):
        if offset is None:
            offset = 0
        if type(offset) is not int or not 0 <= offset <= fresh.MAX_RECORDS:
            raise ConsumerError('Page offset must be a bounded nonnegative integer')
    try:
        with _Snapshot(bundle_directory) as (snapshot, raw):
            hashes = {
                'original.xml': pins.source_sha256,
                'ATTRIBUTION.md': pins.attribution_sha256,
                'accession.json': pins.accession_sha256,
                'CHANGES.txt': pins.changes_sha256,
                'records.jsonl': pins.records_sha256,
                'manifest.json': pins.manifest_sha256,
            }
            if any(fresh.sha256(raw[name]) != digest for name, digest in hashes.items()):
                raise ConsumerError('Bundle fingerprint mismatch')
            if raw['CHANGES.txt'] != fresh.CHANGE_NOTICE.encode('utf-8'):
                raise ConsumerError('Exact change notice required')
            base_declaration = fresh.Declaration(pins.source_sha256, pins.attribution_sha256,
                pins.accession_sha256, declaration.accepted_license, declaration.purpose, True)
            manifest = fresh.verify(raw['original.xml'], raw['ATTRIBUTION.md'], raw['accession.json'],
                fresh.Preparation(raw['records.jsonl'], raw['manifest.json']), declaration=base_declaration)
            result = {
                'consumer_version': CONSUMER_VERSION, 'format': fresh.FORMAT,
                'operation': operation, 'warning': fresh.WARNING,
                'license': fresh.LICENSE, 'license_url': fresh.LICENSE_URL,
                'safety': manifest['safety'], 'counts': manifest['counts'],
                'records_can_overlap': True, 'companion_and_output_sha256': hashes,
                'provenance_status': manifest['provenance_status'],
                'parser_contract': manifest['parser_contract'],
                'change_notice': fresh.CHANGE_NOTICE,
            }
            if operation == 'select':
                records = [json.loads(line) for line in raw['records.jsonl'].splitlines()]
                selected = []
                for identifier in xml_ids:
                    hits = [r for r in records if r['source_xml_id'] == identifier]
                    if len(hits) != 1:
                        raise ConsumerError('Selected XML ID is missing or ambiguous')
                    selected.append(hits[0])
                if not reviewed_noncandidates and any(not r['candidate_for_literal_study'] for r in selected):
                    raise ConsumerError('Noncandidate disclosure requires separate explicit review opt-in')
                result.update(records=selected, selection_order='caller_supplied',
                    selection_relation='explicit_selection_not_inferred_support',
                    reviewed_noncandidates=reviewed_noncandidates,
                    attribution_notice=raw['ATTRIBUTION.md'].decode('utf-8'),
                    accession_notice=raw['accession.json'].decode('utf-8'))
            if operation == 'lookup':
                records = [json.loads(line) for line in raw['records.jsonl'].splitlines()]
                hits = [i for i, r in enumerate(records) if r['source_xml_id'] == xml_id]
                if len(hits) != 1:
                    raise ConsumerError('XML ID is missing or ambiguous among selected study units')
                index = hits[0]
                if index - before < 0 or index + after >= len(records):
                    raise ConsumerError('Context window exceeds available records')
                selected = records[index-before:index+after+1]
                if not reviewed_noncandidates and any(not r['candidate_for_literal_study'] for r in selected):
                    raise ConsumerError('Noncandidate disclosure requires separate explicit review opt-in')
                result.update(records=selected, target_record_id=records[index]['id'],
                    context_units_before=before, context_units_after=after,
                    context_relation='adjacent_extracted_units_not_inferred_support',
                    reviewed_noncandidates=reviewed_noncandidates,
                    attribution_notice=raw['ATTRIBUTION.md'].decode('utf-8'),
                    accession_notice=raw['accession.json'].decode('utf-8'))
            if operation in ('search', 'browse'):
                records = [json.loads(line) for line in raw['records.jsonl'].splitlines()]
                eligible = [r for r in records if reviewed_noncandidates or r['candidate_for_literal_study']]
                matches = [r for r in eligible if query in r['parsed_text']] if operation == 'search' else eligible
                if offset > len(matches):
                    raise ConsumerError('Page offset exceeds the selected result set')
                end = min(offset+limit, len(matches))
                result.update(records=matches[offset:end], total_count=len(matches), offset=offset,
                    next_offset=end if end < len(matches) else None,
                    truncated=end < len(matches), limit=limit,
                    search_scope='all_selected_units' if reviewed_noncandidates else 'literal_candidates_only',
                    reviewed_noncandidates=reviewed_noncandidates,
                    attribution_notice=raw['ATTRIBUTION.md'].decode('utf-8'),
                    accession_notice=raw['accession.json'].decode('utf-8'))
                if operation == 'search':
                    result.update(match_count=len(matches), matching='exact_case_sensitive_unicode_substring_no_normalization')
            snapshot.check()
            return result
    except OSError:
        raise ConsumerError('Secure bounded bundle read failed') from None
    except fresh.PreparationError:
        raise ConsumerError('Full pinned-source re-extraction verification failed') from None
