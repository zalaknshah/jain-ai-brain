"""Separate explicit-consent source study; never canonical reasoning or training.

No bundled source text/model, network, database or query logging. Source-derived
outputs retain their pinned CC BY-SA attribution and review flags. Adapted from
the privately reviewed source-study utility; its trained model is NOT imported.
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import unicodedata

SOURCE_SHA256 = 'b2b767a893973aa92306ed9bd35566ee20368634e41db8efa5f2e1bb77250e9a'
RECORDS_SHA256 = 'e063a8c46cac36ad18777148f3e137ced8a7c3c7d24b533176697c522c041c1c'
SOURCE_GIT_BLOB = 'b9985fa57f10168c0552fead9be74a3eb5fefe31'
MANIFEST_SHA256 = '3864b7ea027ef6c6029f0035e2f54bfb621f5a6cc586293f562f64b37de83a76'
ATTRIBUTION_SHA256 = 'fcb6c62cdfbc0ce211100888b00c6916f7ab0f00d4125c681872b78a0486c0fb'
CHANGES_SHA256 = 'c87382f242ac5dad16aea1a17bd377aa28052968452b666af3d9145939f7da5b'
LICENSE = 'CC-BY-SA-4.0'
LICENSE_URL = 'https://creativecommons.org/licenses/by-sa/4.0/'
FEATURES = ['bm25_squashed', 'idf_token_coverage', 'character_trigram_cosine',
            'character_trigram_coverage', 'ordered_token_bigram_coverage']
LEXICAL = [1.0, 0.0, 0.0, 0.0, 0.0]
FIXED_BLEND = [0.55, 0.0, 0.45, 0.0, 0.0]
ADMISSION_FLAGS = ('runtime_admitted', 'training_admitted', 'scholarly_verified')
STUDY_CATEGORIES = ('root_text', 'commentary', 'editorial_note', 'paratext',
                    'quotation_fragment', 'edition_metadata')
WARNING = ('UNREVIEWED SOURCE STUDY ONLY. Exact edition excerpts are not a translation, '
           'doctrinal validation, or advice for business or personal decisions. This is one '
           'Digambara commentary, not the complete Agama canon. Inherited language labels '
           'may include Prakrit quotations or English notes. No modern Hindi translation is supplied.')


class StudyError(ValueError):
    """Fail-closed consent, integrity, or input error."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StudyError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def strict_json(data):
    try:
        return json.loads(data, object_pairs_hook=_strict_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(StudyError('Non-finite JSON: ' + value)))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise StudyError('Malformed JSON') from exc


def read_regular(path: Path, limit: int) -> bytes:
    """POSIX openat: reject symlinks in every component, nonregular files and oversized IO.

    Never resolve symlinks and never follow a second pathname after validating the bytes.
    Component traversal is anchored by directory file descriptors, not check-then-open.
    """
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or '\x00' in str(path):
        raise StudyError('Absolute path without parent traversal required')
    if (not all(hasattr(os, item) for item in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK'))
            or os.open not in os.supports_dir_fd):
        raise StudyError('This adapter requires POSIX no-follow directory IO')
    directory_fd = file_fd = None
    try:
        directory_fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        for component in path.parts[1:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=directory_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise StudyError('Input is not a bounded regular file: ' + str(path))
        chunks = []
        count = 0
        while True:
            part = os.read(file_fd, min(65536, limit + 1 - count))
            if not part:
                break
            chunks.append(part)
            count += len(part)
            if count > limit:
                raise StudyError('Input exceeded byte limit')
        after = os.fstat(file_fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise StudyError('Input changed during read')
        return b''.join(chunks)
    except OSError as exc:
        raise StudyError('Secure read failed for ' + str(path) + ': ' + str(exc)) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _pinned(path, expected, limit=4 * 1024 * 1024):
    raw = read_regular(path, limit)
    if sha256(raw) != expected:
        raise StudyError('Fingerprint mismatch: ' + str(path))
    return raw


def tokens(text):
    """Index-only normalization; displayed source and source parts remain untouched."""
    return tuple(re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', text).casefold()))


def trigrams(ts):
    text = ' '.join(ts)
    return frozenset(text[i:i + 3] for i in range(max(0, len(text) - 2)))


def eligible(record):
    return (record.get('category') in ('root_text', 'commentary')
            and record.get('citation_status') == 'source_identifier_present_unreviewed'
            and record.get('quotation_context_review_required') is False
            and record.get('within_quotation_markup') is False
            and record.get('contains_quotation_markup') is False)


def _validate_records(raw):
    records = [strict_json(line) for line in raw.splitlines() if line.strip()]
    if not records or len(records) > 2000:
        raise StudyError('Invalid record count')
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise StudyError('Record must be an object')
        if not isinstance(record.get('id'), str) or record['id'] in ids:
            raise StudyError('Missing or duplicate record identity')
        ids.add(record['id'])
        if any(record.get(flag) is not False for flag in ADMISSION_FLAGS):
            raise StudyError('Canonical admission flags must remain false')
        if record.get('source_sha256') != SOURCE_SHA256 or record.get('license') != LICENSE:
            raise StudyError('Record provenance mismatch')
        if not isinstance(record.get('text'), str) or sha256(record['text'].encode()) != record.get('text_sha256'):
            raise StudyError('Record text mismatch')
        if not isinstance(record.get('source_text_parts'), list):
            raise StudyError('Missing exact parsed source parts')
        if not isinstance(record.get('source_xml_path'), str):
            raise StudyError('Missing source path')
        for flag in ('within_quotation_markup', 'contains_quotation_markup', 'quotation_context_review_required'):
            if type(record.get(flag)) is not bool:
                raise StudyError('Missing quotation review flag')
        if record['quotation_context_review_required'] != (
                record['within_quotation_markup'] or record['contains_quotation_markup']):
            raise StudyError('Inconsistent quotation flags')
    return records


@dataclass(frozen=True)
class Consent:
    """Caller must explicitly accept this edition, prepared version and license each session."""
    source_sha256: str
    records_sha256: str
    accepted_license: str
    purpose: str
    opted_in: bool


def consent_for_approved_source():
    """Convenience value; does not open anything. Caller must choose to pass it explicitly."""
    return Consent(SOURCE_SHA256, RECORDS_SHA256, LICENSE, 'private-source-study', True)


class PassageIndex:
    """In-memory lexical index. No persistence and no automatic language interpretation."""
    def __init__(self, records):
        self.records = sorted(records, key=lambda r: r['id'])
        self.token_lists = [tokens(r['text']) for r in self.records]
        self.counts = [Counter(t) for t in self.token_lists]
        self.chars = [trigrams(t) for t in self.token_lists]
        self.bigrams = [frozenset(zip(t, t[1:])) for t in self.token_lists]
        self.df = Counter()
        for counts in self.counts:
            self.df.update(counts.keys())
        n = len(records)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in self.df.items()}
        self.oov_idf = math.log(1 + (n + 0.5) / 0.5)
        self.average_length = sum(map(len, self.token_lists)) / max(1, n)

    def feature_rows(self, query):
        qt = tokens(query)
        qs = set(qt)
        qc = trigrams(qt)
        qb = set(zip(qt, qt[1:]))
        weight = sum(self.idf.get(t, self.oov_idf) for t in qs)
        rows = []
        for i, counts in enumerate(self.counts):
            score = 0.0
            length = len(self.token_lists[i])
            for term in qs:
                tf = counts.get(term, 0)
                if tf:
                    score += self.idf.get(term, self.oov_idf) * (tf * 2.2) / (
                        tf + 1.2 * (0.25 + 0.75 * length / max(1, self.average_length)))
            coverage = sum(self.idf.get(t, self.oov_idf) for t in qs if t in counts) / max(weight, 1e-12)
            intersection = len(qc & self.chars[i])
            cosine = intersection / math.sqrt(max(1, len(qc) * len(self.chars[i])))
            ccov = intersection / max(1, len(qc))
            bcov = len(qb & self.bigrams[i]) / max(1, len(qb))
            rows.append((score / (score + 5.0), coverage, cosine, ccov, bcov))
        return rows

    def candidate_features(self, query):
        rows = self.feature_rows(query)
        lexical = sorted(range(len(rows)), key=lambda i: (-rows[i][0], self.records[i]['id']))[:20]
        chars = sorted(range(len(rows)), key=lambda i: (-rows[i][2], self.records[i]['id']))[:20]
        return [(i, rows[i]) for i in sorted(set(lexical) | set(chars))]

    def rank_features(self, candidates, weights):
        return sorted(candidates, key=lambda item: (-sum(w * v for w, v in zip(weights, item[1])),
                                                    self.records[item[0]]['id']))


def source_fingerprints():
    return {'source_sha256': SOURCE_SHA256, 'records_sha256': RECORDS_SHA256,
            'manifest_sha256': MANIFEST_SHA256, 'attribution_sha256': ATTRIBUTION_SHA256,
            'preparation_changes_sha256': CHANGES_SHA256}


class StudySession:
    def __init__(self, consent=None, *, source_path=None, prepared_path=None):
        self._active = False
        self._index = None
        self._records = {}
        if not isinstance(source_path, (str, os.PathLike)) or not isinstance(prepared_path, (str, os.PathLike)):
            raise StudyError('Explicit absolute private source and prepared paths are required')
        source_path, prepared_path = Path(source_path), Path(prepared_path)
        if any(not p.is_absolute() or '..' in p.parts for p in (source_path, prepared_path)):
            raise StudyError('Absolute private paths without parent traversal are required')
        self._bytes = {}
        if not isinstance(consent, Consent) or type(consent.opted_in) is not bool or consent != consent_for_approved_source():
            raise StudyError('Explicit per-session opt-in to this source, dataset, purpose and CC BY-SA 4.0 is required')
        self._bytes = {
            'source': _pinned(source_path, SOURCE_SHA256),
            'records': _pinned(prepared_path / 'records.jsonl', RECORDS_SHA256),
            'manifest': _pinned(prepared_path / 'manifest.json', MANIFEST_SHA256),
            'attribution': _pinned(prepared_path / 'ATTRIBUTION.md', ATTRIBUTION_SHA256, 65536),
            'changes': _pinned(prepared_path / 'CHANGES.md', CHANGES_SHA256, 65536),
        }
        source = self._bytes['source']
        git_blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
        if git_blob != SOURCE_GIT_BLOB:
            raise StudyError('Source Git blob mismatch')
        manifest = strict_json(self._bytes['manifest'])
        expected = {'source_sha256': SOURCE_SHA256, 'records_sha256': RECORDS_SHA256,
                    'attribution_sha256': ATTRIBUTION_SHA256, 'change_notice_sha256': CHANGES_SHA256,
                    'source_git_blob_sha': SOURCE_GIT_BLOB, 'license': LICENSE}
        if any(manifest.get(k) != v for k, v in expected.items()):
            raise StudyError('Manifest binding mismatch')
        records = _validate_records(self._bytes['records'])
        self._records = {r['id']: r for r in records}
        self._index = PassageIndex([r for r in records if eligible(r)])
        self._active = True

    def _require_active(self):
        if not self._active:
            raise StudyError('Session is revoked or inactive; create a new explicitly opted-in session')

    def revoke(self):
        """Disable every further read and discard session references. Not a secure RAM wipe."""
        self._active = False
        self._records.clear()
        self._bytes.clear()
        self._index = None

    def __enter__(self):
        self._require_active()
        return self

    def __exit__(self, *args):
        self.revoke()

    def _envelope(self):
        self._require_active()
        return {'mode': 'private-source-study', 'title': 'Sarvārthasiddhi on the Tattvārthasūtra',
                'edition': 'SARIT digital edition, Jayandra Soni 2022',
                'warning': WARNING, 'license': LICENSE, 'license_url': LICENSE_URL,
                'attribution': self._bytes['attribution'].decode('utf-8'),
                'preparation_changes': self._bytes['changes'].decode('utf-8'),
                'fingerprints': source_fingerprints(),
                'query_persisted': False, 'provider_called': False, 'actions_executed': False,
                'canonical_promoted': False, 'model_loaded': False, 'learned_ranking': False}

    def _present(self, record):
        result = copy.deepcopy(record)
        warnings = [WARNING]
        if not eligible(record):
            warnings.append('EXCLUDED FROM DEFAULT SEARCH AND LEARNING. Literal source inspection only.')
        if record['citation_status'] == 'source_identifier_incomplete':
            warnings.append('INCOMPLETE SOURCE IDENTIFIER: no missing verse number has been inferred.')
        if record['quotation_context_review_required']:
            warnings.append('QUOTATION CONTEXT REQUIRES REVIEW: ancestry or inline quotations are present; no speaker or endorsement is inferred.')
        if record['category'] == 'editorial_note':
            warnings.append('EDITORIAL NOTE, NOT ROOT TEACHING. Targets and source wording are preserved; no silent correction is applied.')
        result.update(title='Sarvārthasiddhi on the Tattvārthasūtra', warnings=warnings,
                      excerpt_normalization='Exact prepared display text; XML parsing normalizes line endings and display collapses whitespace. Exact parsed text parts are included.')
        return result

    def lookup(self, identity):
        self._require_active()
        if not isinstance(identity, str) or len(identity) > 512:
            raise StudyError('Bounded literal identity required')
        record = self._records.get(identity)
        if record is None:
            matches = [r for r in self._records.values() if r['source_xml_path'] == identity]
            record = matches[0] if len(matches) == 1 else None
        response = self._envelope()
        response.update(status='found' if record else 'not_found', results=[self._present(record)] if record else [])
        return response

    def inventory(self):
        """Summarize recorded coverage and review flags without returning passages.

        Counts describe this preparation only, not a complete canon, validated
        language, a reviewed edition, or permission for a new downstream use.
        Fixed buckets avoid echoing arbitrary source metadata as output keys.
        """
        self._require_active()
        def bucket():
            return {'records': 0, 'search_eligible': 0, 'search_excluded': 0}

        categories = {name: bucket() for name in (*STUDY_CATEGORIES, 'unrecognized')}
        chapters = {name: bucket() for name in (*(str(n) for n in range(1, 11)),
                                               'unassigned', 'unrecognized')}
        total = bucket()
        review_flags = {'incomplete_source_identifier': 0,
                        'quotation_context_review_required': 0,
                        'editorial_note': 0}
        for record in self._records.values():
            category = record.get('category')
            category = category if isinstance(category, str) and category in STUDY_CATEGORIES else 'unrecognized'
            chapter = record.get('chapter')
            if chapter is None:
                chapter = 'unassigned'
            elif not isinstance(chapter, str) or chapter not in tuple(str(n) for n in range(1, 11)):
                chapter = 'unrecognized'
            eligibility = 'search_eligible' if eligible(record) else 'search_excluded'
            for counts in (total, categories[category], chapters[chapter]):
                counts['records'] += 1
                counts[eligibility] += 1
            review_flags['incomplete_source_identifier'] += record.get('citation_status') == 'source_identifier_incomplete'
            review_flags['quotation_context_review_required'] += record['quotation_context_review_required']
            review_flags['editorial_note'] += category == 'editorial_note'
        response = self._envelope()
        response.update(status='inventory', totals=total, by_category=categories,
                        by_chapter=chapters, review_flags=review_flags,
                        review_flag_counts_may_overlap=True,
                        record_content_included=False,
                        admission_counts={flag: 0 for flag in ADMISSION_FLAGS},
                        reason='Metadata counts from the pinned preparation only. Search eligibility is a mechanical filter, '
                               'not scholarly review or runtime/training admission. Review flags may overlap and do not '
                               'enumerate every reason a record is excluded. No passage, identifier or source path is returned.')
        return response

    def browse(self, *, offset=0, limit=5, chapter=None, category=None):
        """Inspect exact records in pinned preparation order, without relevance ranking.

        Filters select recorded metadata only. Adjacent entries do not establish
        a root/commentary relationship, speaker, endorsement or doctrinal context.
        Each request is stateless and remains bound to the same pinned preparation.
        """
        self._require_active()
        _validate_browse_options(offset, limit, chapter, category)
        selected = [record for record in self._records.values()
                    if (chapter is None or record.get('chapter') == chapter)
                    and (category is None or record.get('category') == category)]
        total = len(selected)
        if offset > total:
            raise StudyError('Browse offset exceeds the number of records matching these filters')
        page = selected[offset:offset + limit]
        next_offset = offset + len(page)
        response = self._envelope()
        response.update(status='page' if page else 'complete',
                        results=[self._present(record) for record in page],
                        order='prepared_record_order', offset=offset, limit=limit,
                        total=total, next_offset=next_offset if next_offset < total else None,
                        filters={'chapter': chapter, 'category': category},
                        reason='Literal inspection in preparation order, not relevance or a doctrinal relationship. '
                               'All categories retain their original review warnings; metadata filters make no corrections.')
        return response

    def search(self, query, *, query_language=None, limit=5, ranking='fixed_blend'):
        self._require_active()
        response = self._envelope()
        response.update(status='abstained', results=[], ranking=ranking)
        if not isinstance(query, str) or not 1 <= len(query) <= 512:
            response['reason'] = 'Query must contain 1-512 characters'
            return response
        if query_language != 'sa-Latn':
            response['reason'] = 'Only explicitly labeled Latin-transliterated source-fragment queries are supported; English, Hindi and Gujarati semantics are not supplied'
            return response
        if any(c.isalpha() and 'LATIN' not in unicodedata.name(c, '') for c in query):
            response['reason'] = 'Unsupported script; no translation or transliteration is invented'
            return response
        qt = tokens(query)
        if len(qt) < 2 or not any(t in self._index.df for t in qt):
            response['reason'] = 'Insufficient literal source overlap'
            return response
        if type(limit) is not int or not 1 <= limit <= 20:
            raise StudyError('Result limit must be an integer between 1 and 20')
        if ranking not in ('lexical', 'fixed_blend'):
            raise StudyError('Only untrained lexical or fixed-blend ranking is supported')
        candidates = self._index.candidate_features(query)
        if not candidates or max(features[3] for _, features in candidates) < 0.35:
            response['reason'] = 'Insufficient character overlap; this edition cannot support the query'
            return response
        weights = LEXICAL if ranking == 'lexical' else FIXED_BLEND
        ranked = self._index.rank_features(candidates, weights)[:limit]
        response.update(status='matches', results=[dict(self._present(self._index.records[i]),
                          retrieval_score=sum(w * v for w, v in zip(weights, fs))) for i, fs in ranked],
                        reason='Mechanical source overlap only; no semantic relevance or advice claim')
        return response


MAX_INPUT_BYTES = 4096
MAX_OUTPUT_BYTES = 256 * 1024


def _validate_browse_options(offset, limit, chapter, category):
    if type(offset) is not int or not 0 <= offset <= 2000:
        raise StudyError('Browse offset must be an integer between 0 and 2000')
    if type(limit) is not int or not 1 <= limit <= 20:
        raise StudyError('Result limit must be an integer between 1 and 20')
    if chapter is not None and (not isinstance(chapter, str) or chapter not in tuple(str(n) for n in range(1, 11))):
        raise StudyError('Browse chapter must be an exact string from 1 through 10')
    if category is not None and (not isinstance(category, str) or category not in STUDY_CATEGORIES):
        raise StudyError('Browse category must be one of the documented source categories')


def parse_request(raw):
    """Bounded stdin protocol; source queries never belong in command-line arguments."""
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_INPUT_BYTES:
        raise StudyError('Source-study JSON input must contain 1-4096 bytes')
    request = strict_json(raw)
    if not isinstance(request, dict):
        raise StudyError('Source-study input must be a JSON object')
    operation = request.get('operation')
    if operation == 'inventory':
        if set(request) != {'operation'}:
            raise StudyError('Inventory accepts only operation; no filters, paths or actions')
    elif operation == 'lookup':
        if set(request) != {'operation', 'id'} or not isinstance(request['id'], str) or not 1 <= len(request['id']) <= 512:
            raise StudyError('Lookup requires only operation and a bounded nonempty id')
    elif operation == 'browse':
        if set(request) - {'operation', 'offset', 'limit', 'chapter', 'category'}:
            raise StudyError('Browse accepts only operation, offset, limit, chapter and category')
        if any(key in request and request[key] is None for key in ('chapter', 'category')):
            raise StudyError('Omit unused browse filters; explicit null filters are not supported')
        _validate_browse_options(request.get('offset', 0), request.get('limit', 5),
                                 request.get('chapter'), request.get('category'))
    elif operation == 'search':
        if not {'operation', 'query', 'query_language'} <= set(request) or set(request) - {
                'operation', 'query', 'query_language', 'limit', 'ranking'}:
            raise StudyError('Search requires query and query_language with optional limit and ranking only')
        if not isinstance(request['query'], str) or not 1 <= len(request['query']) <= 512:
            raise StudyError('Query must contain 1-512 characters')
        if not isinstance(request['query_language'], str) or len(request['query_language']) > 32:
            raise StudyError('A bounded query_language declaration is required')
        if type(request.get('limit', 5)) is not int or not 1 <= request.get('limit', 5) <= 20:
            raise StudyError('Result limit must be an integer between 1 and 20')
        if request.get('ranking', 'fixed_blend') not in ('lexical', 'fixed_blend'):
            raise StudyError('Only untrained lexical or fixed-blend ranking is supported')
    else:
        raise StudyError('Only inventory, lookup, browse and search are supported; no training or action operation')
    return request


def run_request(raw, *, consent, source_path, prepared_path):
    request = parse_request(raw)
    with StudySession(consent, source_path=source_path, prepared_path=prepared_path) as session:
        if request['operation'] == 'inventory':
            result = session.inventory()
        elif request['operation'] == 'lookup':
            result = session.lookup(request['id'])
        elif request['operation'] == 'browse':
            result = session.browse(offset=request.get('offset', 0), limit=request.get('limit', 5),
                                    chapter=request.get('chapter'), category=request.get('category'))
        else:
            result = session.search(request['query'], query_language=request['query_language'],
                                    limit=request.get('limit', 5), ranking=request.get('ranking', 'fixed_blend'))
        serialized = json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n'
        if len(serialized.encode('utf-8')) > MAX_OUTPUT_BYTES:
            raise StudyError('Source-study response exceeds the private 256 KiB output limit')
        return serialized
