"""Offline exact-span translation work packets, never training admission."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

MAX_SOURCE_BYTES = 4 * 1024 * 1024
METADATA = {'work', 'edition', 'source_url', 'rights_basis', 'rights_notice',
            'attribution', 'declared_source_language', 'text_role', 'locator'}
SCOPE = ('Private preparation only. Source language, text role, rights and edition are '
         'operator declarations, not verified facts. OCR, translation and scholarly review '
         'remain pending. No model call, generated translation, corpus or training admission.')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                   separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


def prepare(source: bytes, specification: dict) -> dict:
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_SOURCE_BYTES:
        raise ValueError('source must contain one to 4194304 bytes')
    if not isinstance(specification, dict) or set(specification) != {'source_sha256', 'metadata', 'spans'}:
        raise ValueError('specification requires source_sha256, metadata and spans')
    actual = hashlib.sha256(source).hexdigest()
    if specification['source_sha256'] != actual:
        raise ValueError('source digest mismatch')
    metadata = specification['metadata']
    if not isinstance(metadata, dict) or set(metadata) != METADATA:
        raise ValueError('all provenance fields are required')
    for value in metadata.values():
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError('provenance must be bounded nonempty text')
        value.encode('utf-8', errors='strict')
    spans = specification['spans']
    if not isinstance(spans, list) or not 1 <= len(spans) <= 64:
        raise ValueError('one to 64 explicit source spans required')
    tasks, ids = [], set()
    for span in spans:
        if not isinstance(span, dict) or set(span) != {'id', 'byte_start', 'byte_end', 'locator'}:
            raise ValueError('invalid span schema')
        identity, start, end = span['id'], span['byte_start'], span['byte_end']
        if not isinstance(identity, str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}', identity) or identity in ids:
            raise ValueError('invalid or duplicate span ID')
        ids.add(identity)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source) or end-start > 24000:
            raise ValueError('invalid or oversized byte span')
        locator = span['locator']
        if not isinstance(locator, str) or not locator.strip() or len(locator) > 1000:
            raise ValueError('span locator required')
        # No normalization, OCR correction or automatic verse segmentation.
        selected = source[start:end]
        try:
            text = selected.decode('utf-8', errors='strict')
        except UnicodeError as error:
            raise ValueError('span must align with exact UTF-8 characters') from error
        if not text.strip():
            raise ValueError('empty source span')
        evidence = {'source_sha256': actual, 'span': dict(span), 'metadata': dict(metadata),
                    'excerpt_sha256': hashlib.sha256(selected).hexdigest()}
        tasks.append({'id': identity, 'source': evidence, 'source_text': text,
                      'source_binding_sha256': digest(evidence),
                      'source_review': {'language': 'pending', 'role': 'pending', 'ocr': 'pending', 'rights_for_training': 'pending'},
                      'translations': {language: {'draft': None, 'translator': None, 'reviewer': None,
                                                'review_status': 'pending', 'uncertainties': []}
                                       for language in ('gu', 'hi', 'en')}})
    return {'format': 'jace-private-translation-work-v1', 'tasks': tasks,
            'training_admitted': False, 'runtime_admitted': False,
            'public_release_approved': False, 'scope': SCOPE}



def prepare_with_scans(source: bytes, specification: dict, scans: dict, bindings: dict) -> dict:
    """Bind supplied scan bytes to every span; never attest visual correspondence.

    Scans map stable IDs to bytes. Bindings map span IDs to scan_id, sha256,
    locator, source_url. This function performs no filesystem or network IO.
    """
    packet = prepare(source, specification)
    if not isinstance(scans, dict) or not 1 <= len(scans) <= 64:
        raise ValueError('one to 64 scan inputs required')
    for identity, data in scans.items():
        if not isinstance(identity, str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}', identity):
            raise ValueError('invalid scan ID')
        if not isinstance(data, bytes) or not 0 < len(data) <= 8 * 1024 * 1024:
            raise ValueError('invalid scan bytes')
    if sum(map(len, scans.values())) > 32 * 1024 * 1024:
        raise ValueError('aggregate scans exceed limit')
    if not isinstance(bindings, dict) or set(bindings) != {t['id'] for t in packet['tasks']}:
        raise ValueError('exactly one scan binding per source span required')
    used = set()
    for task in packet['tasks']:
        binding = bindings[task['id']]
        if not isinstance(binding, dict) or set(binding) != {'scan_id', 'sha256', 'locator', 'source_url'}:
            raise ValueError('invalid scan binding fields')
        for value in binding.values():
            if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                raise ValueError('invalid scan binding text')
            value.encode('utf-8', errors='strict')
        scan_id = binding['scan_id']
        if scan_id not in scans or hashlib.sha256(scans[scan_id]).hexdigest() != binding['sha256']:
            raise ValueError('scan bytes or digest mismatch')
        used.add(scan_id)
        # Copy declarations: later caller mutations must not invalidate evidence.
        evidence = {'source_binding_sha256': task['source_binding_sha256'],
                    'scan': dict(binding)}
        task['scan_evidence'] = evidence
        task['scan_binding_sha256'] = digest(evidence)
        task['source_review']['scan_correspondence'] = 'pending'
    if used != set(scans):
        raise ValueError('unreferenced scan input')
    packet['format'] = 'jace-private-scan-linked-translation-work-v1'
    packet['scan_scope'] = ('Byte identity only. Inputs are not decoded as images; no scan/source '
                            'correspondence, authenticity, OCR accuracy or language is verified. '
                            'All translation slots and admission gates remain unchanged.')
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('specification', type=Path)
    parser.add_argument('output', type=Path, help='new private local file; never overwritten')
    args = parser.parse_args()
    try:
        with args.source.open('rb') as handle:
            source = handle.read(MAX_SOURCE_BYTES + 1)
        with args.specification.open('rb') as handle:
            raw = handle.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError('specification exceeds limit')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate specification key')
                result[key] = value
            return result
        specification = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        packet = prepare(source, specification)
        with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
            json.dump(packet, handle, ensure_ascii=True, indent=2)
            handle.write('\n')
        print(json.dumps({'task_count': len(packet['tasks']), 'training_admitted': False,
                          'runtime_admitted': False}))
        return 0
    except (OSError, ValueError, UnicodeError):
        print('Preparation failed: invalid input or unavailable output; no source text emitted.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
