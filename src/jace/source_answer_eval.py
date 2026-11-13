"""Offline saved-answer evaluation; never an automatic entailment or safety judge."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import re

from .model_output import check_model_output, checked_text
from .models import CanonicalEntry

MAX_CASES = 256
VERDICTS = ('supported', 'unsupported', 'uncertain')
SCOPE = ('Mechanical citation results and supplied human-review annotations only. '
         'Reviewer identity, expertise, truth, Jain reasoning and robot safety are not verified. '
         'No corpus is admitted, model executed or runtime decision authorized.')


def _digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def _case(raw):
    if not isinstance(raw, dict) or set(raw) != {'id', 'question', 'require_citation', 'evidence'}:
        raise ValueError('case requires id, question, require_citation and evidence')
    if not isinstance(raw['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', raw['id']):
        raise ValueError('invalid case ID')
    checked_text(raw['question'], 'question', 4096)
    if type(raw['require_citation']) is not bool or not isinstance(raw['evidence'], list) or len(raw['evidence']) > 20:
        raise ValueError('invalid citation requirement or evidence list')
    entries = []
    for value in raw['evidence']:
        if not isinstance(value, dict): raise ValueError('source must be an object')
        try:
            entry = CanonicalEntry(**value)
            serialized = json.dumps(asdict(entry), ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError('invalid source record') from error
        if len(serialized) > 40000: raise ValueError('source record exceeds limit')
        for name in ('entry_id', 'title', 'principle', 'guidance', 'source', 'language'):
            checked_text(getattr(entry, name), 'source ' + name, 20000, allow_crlf=name == 'principle')
        for name in ('work', 'edition', 'location', 'license', 'source_sha256'):
            value = getattr(entry, name)
            if value is not None: checked_text(value, 'source ' + name, 1000)
        if type(entry.verified) is not bool or any(
                value is not None and type(value) is not int
                for value in (entry.source_byte_start, entry.source_byte_end)):
            raise ValueError('invalid source flags or byte bounds')
        entries.append(entry)
    return entries


def evaluate_source_answers(cases, outputs, reviews=None):
    """Compare saved answers with sources; annotations are assertions, not credentials.

    ``review_binding_sha256`` binds the exact case and raw output. Report rows omit
    question, source and answer text so ordinary summaries need not disclose them.
    Missing outputs remain in the denominator. No aggregate semantic pass exists.
    """
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError('one to 256 cases required')
    if not isinstance(outputs, dict) or (reviews is not None and not isinstance(reviews, dict)):
        raise ValueError('outputs and reviews must be objects keyed by case ID')
    reviews = {} if reviews is None else reviews
    parsed = [(_case(case), case) for case in cases]
    ids = [case['id'] for _, case in parsed]
    if len(set(ids)) != len(ids) or set(outputs) - set(ids) or set(reviews) - set(ids):
        raise ValueError('duplicate case or unknown output/review ID')
    rows = []
    for evidence, case in parsed:
        case_id = case['id']
        output = outputs.get(case_id)
        if case_id in outputs and (not isinstance(output, str) or len(output) > 16000):
            raise ValueError('saved output must be bounded text; omit absent outputs')
        binding = _digest({'case': case, 'output': output})
        mechanical = 'missing'
        citation_requirement = False
        if output is not None:
            try:
                result = check_model_output(output, evidence)
                mechanical = 'accepted'
                citation_requirement = bool(result.citations) or not case['require_citation']
            except ValueError:
                mechanical = 'rejected'
        verdict = None
        if case_id in reviews:
            review = reviews[case_id]
            if not isinstance(review, dict) or set(review) != {'review_binding_sha256', 'verdict', 'reviewer', 'rationale'}:
                raise ValueError('invalid review schema')
            if output is None or review['review_binding_sha256'] != binding:
                raise ValueError('review lacks an output or is stale for this case/source/answer')
            if review['verdict'] not in VERDICTS: raise ValueError('invalid review verdict')
            checked_text(review['reviewer'], 'reviewer label', 128)
            checked_text(review['rationale'], 'review rationale', 4096)
            verdict = review['verdict']
        rows.append({'id': case_id, 'mechanical': mechanical,
                     'citation_requirement_met': citation_requirement,
                     'review_binding_sha256': binding, 'human_verdict': verdict})
    return {'case_count': len(rows), 'output_count': len(outputs),
            'mechanically_accepted': sum(row['mechanical'] == 'accepted' for row in rows),
            'citation_requirement_met': sum(row['citation_requirement_met'] for row in rows),
            'review_count': len(reviews), 'unreviewed_count': len(rows) - len(reviews),
            'human_verdict_counts': {v: sum(row['human_verdict'] == v for row in rows) for v in VERDICTS},
            'complete_output_coverage': len(outputs) == len(rows),
            'complete_review_coverage': len(reviews) == len(rows),
            'semantic_quality_verified': False, 'runtime_admitted': False,
            'cases': rows, 'scope': SCOPE}


def compare_source_answers(cases, baseline, candidate):
    """Paired, offline comparison using exactly one common declared case set.

    Each run contains outputs and optional reviews. This deliberately accepts raw
    inputs, not summary reports, so mismatched cases cannot silently be joined.
    Changes in supplied human verdicts are not independently verified gains.
    """
    for run in (baseline, candidate):
        if not isinstance(run, dict) or set(run) not in ({'outputs'}, {'outputs', 'reviews'}):
            raise ValueError('each run requires outputs and optional reviews only')
    before = evaluate_source_answers(cases, baseline['outputs'], baseline.get('reviews'))
    after = evaluate_source_answers(cases, candidate['outputs'], candidate.get('reviews'))
    pairs = []
    for left, right in zip(before['cases'], after['cases']):
        pairs.append({
            'id': left['id'],
            'baseline': left,
            'candidate': right,
            'output_lost': left['mechanical'] != 'missing' and right['mechanical'] == 'missing',
            'mechanical_acceptance_lost': left['mechanical'] == 'accepted' and right['mechanical'] != 'accepted',
            'citation_requirement_lost': left['citation_requirement_met'] and not right['citation_requirement_met'],
            'supported_annotation_lost': left['human_verdict'] == 'supported' and right['human_verdict'] != 'supported',
        })
    # Canonical ordering makes the declared-case binding independent of list order,
    # while any change in a question, source or requirement changes the binding.
    case_set_hash = _digest(sorted(cases, key=lambda case: case['id']))
    transitions = {}
    for pair in pairs:
        left = pair['baseline']['human_verdict'] or 'unreviewed'
        right = pair['candidate']['human_verdict'] or 'unreviewed'
        key = left + '_to_' + right
        transitions[key] = transitions.get(key, 0) + 1
    return {
        'case_count': len(cases), 'declared_case_set_sha256': case_set_hash,
        'baseline': before, 'candidate': after, 'pairs': pairs,
        'coverage': {
            'paired_outputs': sum(p['baseline']['mechanical'] != 'missing' and p['candidate']['mechanical'] != 'missing' for p in pairs),
            'paired_reviews': sum(p['baseline']['human_verdict'] is not None and p['candidate']['human_verdict'] is not None for p in pairs),
        },
        'loss_counts': {key: sum(p[key] for p in pairs) for key in (
            'output_lost', 'mechanical_acceptance_lost', 'citation_requirement_lost', 'supported_annotation_lost')},
        'human_annotation_transitions': transitions,
        'semantic_quality_verified': False, 'runtime_admitted': False,
        'winner_selected': False, 'scope': SCOPE,
    }
