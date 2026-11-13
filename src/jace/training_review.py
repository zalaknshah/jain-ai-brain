"""Offline, declaration-based Prakrit training review. No translation or training.

Whole UTF-8 books are retained privately for independently repeatable byte-span
checks. Only approved example rows reach the training/evaluation consumer.
Nothing here authenticates reviewers or proves rights or scholarly correctness.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from . import source_bundle as sb

POLICY = 'jace-prakrit-training-review-v1'
DRAFT = 'jace-prakrit-training-draft-v1'
REPORT = 'jace-prakrit-training-decisions-v1'
PURPOSE = 'private_local_training_and_evaluation'
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
SCOPES = ['local_retention', 'training', 'evaluation', 'derivative_weights']
WARNING = ('Private review/export retains WHOLE original books, including unapproved passages. '
           'Only approved example rows may enter optimization/evaluation. No sharing, provider '
           'transmission, model release, translation or training is authorized by this workflow.')


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _revision(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError('invalid ' + label + ' fields')


def _text(value, label, limit=1000):
    return sb.checked_text(value, label, limit)


def _id(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) is None:
        raise ValueError('invalid training example ID')


def read_json(path):
    """Descriptor-safe, bounded private workflow input; no native Windows fallback."""
    sb._require_safe_io()
    absolute, parts = sb._parts(path)
    try:
        with sb._DirectoryChain(absolute, parts[:-1]) as chain:
            raw = sb._read_regular(chain.fd, parts[-1], MAX_MANIFEST_BYTES, chain)
            value = sb._json(raw.decode('utf-8', errors='strict'))
            chain.verify()
            return value
    except (OSError, UnicodeError) as error:
        raise ValueError('cannot safely read private training review JSON') from error


def _validate_provenance(provenance):
    _fields(provenance, 'purpose books records', 'training provenance')
    if provenance['purpose'] != PURPOSE:
        raise ValueError('explicit private training/evaluation purpose is required')
    books, records = provenance['books'], provenance['records']
    if not isinstance(books, dict) or not 1 <= len(books) <= sb.MAX_SOURCES:
        raise ValueError('bounded book inventory required')
    if not isinstance(records, dict) or not 2 <= len(records) <= 512:
        raise ValueError('bounded training/evaluation example inventory required')
    total = 0
    for digest, book in books.items():
        sb._digest(digest)
        _fields(book, 'text work edition source language license attribution rights_evidence', 'book')
        for name in ('work', 'edition', 'source', 'license', 'attribution', 'rights_evidence'):
            _text(book[name], 'book ' + name)
        if book['language'] not in ('pra', 'pra-Deva', 'pra-Latn'):
            raise ValueError('an explicit Prakrit source language declaration is required')
        if not isinstance(book['text'], str):
            raise ValueError('book text must be strict UTF-8 text')
        raw = book['text'].encode('utf-8', errors='strict')
        total += len(raw)
        if not raw or len(raw) > sb.MAX_SOURCE_BYTES or total > sb.MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('whole-book byte budget exceeded')
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('whole-book SHA256 mismatch')
    used, spans = set(), {}
    for key, record in records.items():
        _id(key)
        _fields(record, 'row split book_sha256 start end source_text target_language origin translator translation_license translation_attribution translation_rights_evidence', 'training example')
        row = record['row']
        _fields(row, 'id instruction response', 'training row')
        if row['id'] != key or record['split'] not in ('train', 'evaluation'):
            raise ValueError('record ID/split mismatch')
        for name in ('instruction', 'response'):
            _text(row[name], name, 4096)
        digest = sb._digest(record['book_sha256'])
        if digest not in books:
            raise ValueError('unknown original book')
        used.add(digest)
        book = books[digest]
        raw = book['text'].encode('utf-8')
        start, end = record['start'], record['end']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
            raise ValueError('invalid original byte span')
        try:
            original = raw[start:end].decode('utf-8', errors='strict')
        except UnicodeError as error:
            raise ValueError('original span cuts a UTF-8 character') from error
        _text(record['source_text'], 'source excerpt', 4096)
        if original != record['source_text']:
            raise ValueError('original excerpt does not match exact book bytes')
        # Any overlapping source bytes, even through translations, stay in one split.
        for prior_start, prior_end, prior_split in spans.setdefault(digest, []):
            if start < prior_end and prior_start < end and prior_split != record['split']:
                raise ValueError('overlapping original spans cross training/evaluation splits')
        spans[digest].append((start, end, record['split']))
        if record['origin'] == 'original':
            if (record['target_language'] != book['language'] or row['response'] != original
                    or any(record[name] != '' for name in ('translator', 'translation_license', 'translation_attribution', 'translation_rights_evidence'))):
                raise ValueError('invalid original-text lineage')
        elif record['origin'] in ('human_translation', 'machine_translation'):
            if record['target_language'] not in ('gu', 'hi', 'en'):
                raise ValueError('translation target must be Gujarati, Hindi or English')
            for name in ('translator', 'translation_license', 'translation_attribution', 'translation_rights_evidence'):
                _text(record[name], name)
        else:
            raise ValueError('unknown translation origin')
    if used != set(books):
        raise ValueError('unreferenced books are not accepted')


def _record_revision(provenance, record):
    return _revision({'record': record, 'book_revision': _revision(provenance['books'][record['book_sha256']]), 'policy': POLICY})


def _pending(revision, roles):
    return {'revision': revision, **{role: {'decision': 'pending', 'reviewer': '', 'evidence': '',
                **({'scopes': []} if role == 'rights' else {'qualified': False})} for role in roles}}


def review_template(provenance):
    _validate_provenance(provenance)
    return {'format': REPORT, 'policy': POLICY, 'draft_revision': _revision(provenance),
            'books': {digest: _pending(_revision(book), ('rights',)) for digest, book in provenance['books'].items()},
            'records': {key: _pending(_record_revision(provenance, record), ('rights', 'content', 'translation'))
                        for key, record in provenance['records'].items()}}


def _approved(decision, role):
    _fields(decision, 'decision reviewer evidence ' + ('scopes' if role == 'rights' else 'qualified'), role + ' decision')
    if decision['decision'] not in ('approved', 'rejected', 'pending'):
        raise ValueError('unknown human review decision')
    # Validate even negative/pending states so malformed metadata never passes silently.
    for name in ('reviewer', 'evidence'):
        if not isinstance(decision[name], str) or len(decision[name]) > 1000:
            raise ValueError('invalid review declaration')
    if role == 'rights':
        if not isinstance(decision['scopes'], list) or any(not isinstance(s, str) or s not in SCOPES for s in decision['scopes']):
            raise ValueError('invalid rights scope')
    elif type(decision['qualified']) is not bool:
        raise ValueError('qualified review must be a boolean declaration')
    if decision['decision'] != 'approved':
        return False
    _text(decision['reviewer'], 'human reviewer')
    _text(decision['evidence'], 'human review evidence/rationale')
    if role == 'rights':
        if sorted(decision['scopes']) != sorted(SCOPES):
            raise ValueError('training, evaluation, retention and derivative-weight rights review required')
    elif decision['qualified'] is not True:
        raise ValueError('explicit qualified human review declaration required')
    return True


def _selected(provenance, report, *, draft):
    _fields(report, 'format policy draft_revision books records', 'decision report')
    if report['format'] != REPORT or report['policy'] != POLICY:
        raise ValueError('unsupported training review policy')
    sb._digest(report['draft_revision'])
    if draft and report['draft_revision'] != _revision(provenance):
        raise ValueError('stale draft review')
    for name in ('books', 'records'):
        if not isinstance(report[name], dict) or set(report[name]) != set(provenance[name]):
            raise ValueError('decision report must cover every ' + name + ' entry exactly once')
    books = {}
    for digest, book in provenance['books'].items():
        decision = report['books'][digest]
        _fields(decision, 'revision rights', 'book review')
        if decision['revision'] != _revision(book):
            raise ValueError('stale book rights review')
        books[digest] = _approved(decision['rights'], 'rights')
    selected = {}
    for key, record in provenance['records'].items():
        decision = report['records'][key]
        _fields(decision, 'revision rights content translation', 'example review')
        if decision['revision'] != _record_revision(provenance, record):
            raise ValueError('stale example/translation review')
        checks = [_approved(decision[role], role) for role in ('rights', 'content', 'translation')]
        # Originals need qualified original-text review, not a fictional translation review.
        if record['origin'] == 'original':
            checks[2] = True
        if books[record['book_sha256']] and all(checks):
            selected[key] = record
    return selected


def validate_admitted(manifest, splits):
    """Called by the real dataset consumer on every preflight/snapshot/recheck."""
    _fields(manifest, 'schema_version data_kind source license rights_reviewed content_reviewed contains_personal_data train_sha256 evaluation_sha256 provenance review', 'reviewed training manifest')
    if (type(manifest['schema_version']) is not int or manifest['schema_version'] != 3
            or manifest['data_kind'] != 'reviewed_prakrit'
            or manifest['rights_reviewed'] is not True or manifest['content_reviewed'] is not True
            or manifest['contains_personal_data'] is not False):
        raise ValueError('explicit reviewed Prakrit, non-personal dataset declarations required')
    provenance = manifest['provenance']
    _validate_provenance(provenance)
    selected = _selected(provenance, manifest['review'], draft=False)
    if set(selected) != set(provenance['records']):
        raise ValueError('unapproved material is blocked from training admission')
    for name, rows in zip(('train', 'evaluation'), splits):
        expected = [record['row'] for record in selected.values() if record['split'] == name]
        if sorted(rows, key=lambda row: row['id']) != sorted(expected, key=lambda row: row['id']):
            raise ValueError('training rows differ from exactly reviewed examples')


def _publish(output, files):
    """Private descriptor-pinned publication; atomic no-overwrite final rename."""
    sb._require_publication_io()
    absolute, parts = sb._parts(output)
    with sb._DirectoryChain(absolute, parts[:-1]) as chain:
        parent = chain.fd
        stage = '.jace-training-review-' + secrets.token_hex(16)
        os.mkdir(stage, 0o700, dir_fd=parent)
        fd = None
        published = False
        try:
            fd = chain.descend(parent, stage)
            os.fchmod(fd, 0o700)
            for name, raw in files.items():
                if len(raw) > MAX_MANIFEST_BYTES:
                    raise ValueError('training review output exceeds byte limit')
                sb._write_private(fd, name, raw)
                if sb._read_regular(fd, name, MAX_MANIFEST_BYTES, chain) != raw:
                    raise ValueError('training review output changed during publication')
            chain.verify()
            os.fsync(fd)
            os.fsync(parent)
            sb._rename_noreplace(parent, stage, parts[-1])
            published = True
        finally:
            if not published:
                if fd is None:
                    os.rmdir(stage, dir_fd=parent)
                else:
                    for name in files:
                        try:
                            os.unlink(name, dir_fd=fd)
                        except FileNotFoundError:
                            pass
                    if sb._identity(os.stat(stage, dir_fd=parent, follow_symlinks=False)) != sb._identity(os.fstat(fd)):
                        raise ValueError('private training staging directory changed')
                    os.rmdir(stage, dir_fd=parent)


def prepare_review(plan_path, output, *, confirm_copy=False):
    if confirm_copy is not True:
        raise ValueError('explicit whole-book confirm_copy=True required before any input reads')
    sb._require_publication_io()
    plan = read_json(plan_path)
    _fields(plan, 'books records', 'training review plan')
    if not isinstance(plan['books'], dict) or not 1 <= len(plan['books']) <= sb.MAX_SOURCES:
        raise ValueError('bounded explicit book file inventory required')
    books = {}
    total = 0
    for digest, declaration in plan['books'].items():
        sb._digest(digest)
        _fields(declaration, 'path work edition source language license attribution rights_evidence', 'book plan')
        if not isinstance(declaration['path'], str) or not declaration['path'].startswith('/') or Path(declaration['path']).suffix.lower() != '.txt':
            raise ValueError('explicit absolute UTF-8 .txt book paths are required')
        raw = sb.read_source_file(declaration['path'])
        total += len(raw)
        if total > sb.MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('aggregate whole-book byte budget exceeded')
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('selected book does not match expected SHA256')
        books[digest] = {**{key: value for key, value in declaration.items() if key != 'path'}, 'text': raw.decode('utf-8')}
    provenance = {'purpose': PURPOSE, 'books': books, 'records': plan['records']}
    report = review_template(provenance)  # All decisions pending, never implicit approval.
    _publish(output, {'draft.json': _bytes({'format': DRAFT, 'provenance': provenance}), 'decisions.json': _bytes(report)})
    return Path(output) / 'draft.json'


def export_review(draft_path, decisions_path, output, *, confirm_export=False, declare_no_personal_data=False):
    if confirm_export is not True or declare_no_personal_data is not True:
        raise ValueError('explicit private whole-book export and no-personal-data declarations required')
    sb._require_publication_io()
    draft, report = read_json(draft_path), read_json(decisions_path)
    _fields(draft, 'format provenance', 'training review draft')
    if draft['format'] != DRAFT:
        raise ValueError('unsupported training draft')
    provenance = draft['provenance']
    _validate_provenance(provenance)
    selected = _selected(provenance, report, draft=True)
    book_ids = {record['book_sha256'] for record in selected.values()}
    exported = {'purpose': PURPOSE, 'books': {key: value for key, value in provenance['books'].items() if key in book_ids}, 'records': selected}
    receipt = copy.deepcopy(report)
    receipt['books'] = {key: value for key, value in receipt['books'].items() if key in book_ids}
    receipt['records'] = {key: value for key, value in receipt['records'].items() if key in selected}
    files = {}
    for split in ('train', 'evaluation'):
        rows = [record['row'] for record in selected.values() if record['split'] == split]
        if not rows:
            raise ValueError('both train and evaluation need approved examples; nothing exported')
        files[split + '.jsonl'] = b''.join(_bytes(row) + b'\n' for row in rows)
    manifest = {'schema_version': 3, 'data_kind': 'reviewed_prakrit', 'source': 'Explicit private Prakrit training review',
                'license': 'Per-book and per-translation rights declarations; no blanket relicensing',
                'rights_reviewed': True, 'content_reviewed': True, 'contains_personal_data': False,
                'train_sha256': hashlib.sha256(files['train.jsonl']).hexdigest(),
                'evaluation_sha256': hashlib.sha256(files['evaluation.jsonl']).hexdigest(),
                'provenance': exported, 'review': receipt}
    # Reuse the actual consumer before writing anything, including normal row/leakage budgets.
    from .training import _parse_splits
    splits = _parse_splits([files['train.jsonl'], files['evaluation.jsonl']])
    validate_admitted(manifest, splits)
    files['manifest.json'] = _bytes(manifest)
    _publish(output, files)
    return {'manifest': str(Path(output) / 'manifest.json'), 'approved_records': len(selected),
            'blocked_records': len(provenance['records']) - len(selected), 'training_started': False, 'warning': WARNING}
