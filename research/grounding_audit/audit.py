"""Research-only alignment diagnostics; never rights, scholarly or training admission."""
from __future__ import annotations
import hashlib

MAX_BYTES = 1024 * 1024
MAX_ROWS = 512

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4096

def audit(sources: dict, rows: list) -> dict:
    """Audit caller-supplied candidates without file/network IO or text in output.

    Source bytes must be supplied explicitly; this function cannot authenticate
    acquisition, permissions or reviewers. Exact quotation is not entailment.
    """
    if not isinstance(sources, dict) or len(sources) > 32 or not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('bounded source map and row list required')
    results, seen = [], set()
    for row in rows:
        errors, review = [], []
        if not isinstance(row, dict):
            raise ValueError('each candidate must be a mapping')
        rid = row.get('id')
        if not nonempty(rid) or rid in seen:
            raise ValueError('unique nonempty candidate IDs required')
        seen.add(rid)
        source = sources.get(row.get('source_id')) if isinstance(row.get('source_id'), str) else None
        if not isinstance(source, dict):
            errors.append('unresolved_source')
            source = {}
        raw = source.get('bytes')
        valid_bytes = isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES
        if valid_bytes:
            try:
                raw.decode('utf-8')
            except UnicodeError:
                errors.append('invalid_source_utf8')
        if not valid_bytes:
            errors.append('missing_or_oversized_source_bytes')
        for field in ('work', 'edition', 'language', 'acquisition_reference'):
            if not nonempty(source.get(field)):
                errors.append('missing_source_' + field)
        if valid_bytes and (source.get('sha256') != sha(raw) or row.get('source_sha256') != sha(raw)):
            errors.append('source_digest_mismatch')
        start, end = row.get('start'), row.get('end')
        offsets_ok = valid_bytes and type(start) is int and type(end) is int and 0 <= start < end <= len(raw)
        if not offsets_ok:
            errors.append('invalid_byte_span')
        else:
            try:
                # Prefix decoding also prevents accepting a start inside a code point.
                raw[:start].decode('utf-8'); raw[:end].decode('utf-8')
                span = raw[start:end].decode('utf-8')
                if row.get('raw_excerpt') != span:
                    errors.append('raw_excerpt_mismatch')
            except UnicodeError:
                errors.append('invalid_utf8_boundary')
        if not nonempty(row.get('claim')):
            errors.append('missing_claim')
        if not nonempty(row.get('target_language')):
            errors.append('missing_target_language')
        normalized = row.get('normalized_candidate')
        if normalized is not None:
            if not nonempty(normalized):
                errors.append('invalid_normalized_candidate')
            elif normalized != row.get('raw_excerpt'):
                review.append('normalization_diff_requires_review')
        # No aggregate dataset licence or extraction-confidence field is used.
        for field in ('edition_rights_reference', 'edition_training_scope_reference'):
            if not nonempty(source.get(field)):
                review.append('missing_' + field)
        translated = row.get('target_language') != source.get('language')
        if translated:
            for field in ('translator', 'translation_rights_reference', 'translation_review_reference'):
                if not nonempty(row.get(field)):
                    review.append('missing_' + field)
            if row.get('origin') not in ('machine_translation', 'human_translation'):
                errors.append('translation_origin_not_preserved')
        elif row.get('origin') != 'original':
            errors.append('original_origin_required')
        for field in ('rights_review_reference', 'scholarly_review_reference', 'entailment_review_reference'):
            if not nonempty(row.get(field)):
                review.append('missing_' + field)
        results.append({'id': rid, 'structural_errors': errors, 'review_flags': review,
                        'alignment': 'blocked' if errors else 'exact_span_only',
                        'training_admitted': False, 'semantic_entailment_verified': False,
                        'review_identity_verified': False})
    return {'format': 'jace-research-grounding-audit-v1', 'training_admitted': False,
            'source_count': len(sources), 'candidate_count': len(rows), 'rows': results}
