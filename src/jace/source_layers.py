"""Mechanical coverage of caller-declared source layers, never review admission.

Pure in-memory byte/hash checks. Labels are untrusted declarations: this module
cannot see a scan or establish that a label, page identity or reading is correct.
"""
from __future__ import annotations

import hashlib
import re

MAX_SOURCE_BYTES = 1024 * 1024
MAX_SELECTION_BYTES = 65536
MAX_LAYERS = 256
LAYERS = ('main_body', 'editorial_note', 'section_heading', 'running_header', 'printer_signature', 'unclassified')
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
LIMITATIONS = (
    'Coverage applies only to the supplied selection, never a complete page, work or surrounding context.',
    'Labels are caller declarations; byte checks do not verify scan identity, layer correctness, OCR accuracy or scholarship.',
    'Whitespace-only gaps are reported separately, not silently absorbed into a layer.',
    'An unclassified interval remains unresolved even when every byte is assigned.',
    'No source corrections, rights clearance, review approval, runtime admission, training or IO occur.',
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fields(value, expected: set[str]) -> None:
    if (type(value) is not dict or len(value) != len(expected)
            or any(type(key) is not str for key in value) or value.keys() != expected):
        raise ValueError('invalid source layer fields')


def _checked_digest(value) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError('invalid source layer digest')
    return value


def _interval(raw: bytes, start, end, digest) -> dict:
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
        raise ValueError('invalid source layer byte range')
    fragment = raw[start:end]
    try:
        text = fragment.decode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('source layer endpoints must be UTF-8 boundaries') from error
    actual = _digest(fragment)
    if _checked_digest(digest) != actual:
        raise ValueError('source layer span digest mismatch')
    non_whitespace = sum(not character.isspace() for character in text)
    return {'start': start, 'end': end, 'span_sha256': actual,
            'byte_length': end - start, 'non_whitespace_characters': non_whitespace,
            'whitespace_only': non_whitespace == 0}


def audit_source_layers(source_bytes: bytes, selection: dict, layers: list[dict]) -> dict:
    """Check bounded, ordered byte annotations; return text-free coverage evidence.

    ``selection`` has source_sha256, start, end and span_sha256. Every layer has
    start, end, span_sha256 and a fixed layer label. Offsets are zero-based UTF-8
    bytes, end-exclusive. Missing coverage is reported; overlap, stale digests,
    unknown fields, invalid UTF-8 or out-of-order intervals reject the whole call.
    No arbitrary metadata is accepted or echoed. No input is changed.
    """
    if type(source_bytes) is not bytes or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES:
        raise ValueError('source_bytes must contain 1 through 1048576 bytes')
    try:
        source_bytes.decode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('source_bytes must be valid UTF-8') from error
    _fields(selection, {'source_sha256', 'start', 'end', 'span_sha256'})
    source_digest = _digest(source_bytes)
    if _checked_digest(selection['source_sha256']) != source_digest:
        raise ValueError('source digest mismatch')
    selected = _interval(source_bytes, selection['start'], selection['end'], selection['span_sha256'])
    if selected['byte_length'] > MAX_SELECTION_BYTES or selected['whitespace_only']:
        raise ValueError('selection must contain non-whitespace and at most 65536 bytes')
    if type(layers) is not list or len(layers) > MAX_LAYERS:
        raise ValueError('layers must be a list of at most 256 intervals')
    checked, gaps = [], []
    previous = selected['start']

    def gap(start: int, end: int) -> None:
        if start < end:
            gaps.append(_interval(source_bytes, start, end, _digest(source_bytes[start:end])))

    for ordinal, layer in enumerate(layers, 1):
        _fields(layer, {'start', 'end', 'span_sha256', 'layer'})
        label = layer['layer']
        if type(label) is not str or label not in LAYERS:
            raise ValueError('unknown source layer label')
        row = _interval(source_bytes, layer['start'], layer['end'], layer['span_sha256'])
        if row['start'] < previous or row['end'] > selected['end']:
            raise ValueError('source layers must be ordered, disjoint and inside the selection')
        gap(previous, row['start'])
        checked.append({'ordinal': ordinal, 'layer': label, **row})
        previous = row['end']
    gap(previous, selected['end'])
    unassigned = sum(row['non_whitespace_characters'] for row in gaps)
    unclassified = sum(row['non_whitespace_characters'] for row in checked if row['layer'] == 'unclassified')
    return {'schema_version': 1, 'mode': 'source_layer_coverage_audit',
            'source_sha256': source_digest, 'source_byte_length': len(source_bytes),
            'selection': selected, 'layers': checked, 'gaps': gaps,
            'layer_counts': {label: sum(row['layer'] == label for row in checked) for label in LAYERS},
            'selection_fully_partitioned': not gaps,
            'all_selection_non_whitespace_assigned': unassigned == 0,
            'all_selection_non_whitespace_classified': unassigned == 0 and unclassified == 0,
            'unassigned_non_whitespace_characters': unassigned,
            'unclassified_non_whitespace_characters': unclassified,
            'source_text_included': False, 'source_bytes_changed': False,
            'scan_identity_verified': False, 'layer_labels_verified': False,
            'scholarly_verified': False, 'runtime_admitted': False, 'training_admitted': False,
            'limits': list(LIMITATIONS)}
