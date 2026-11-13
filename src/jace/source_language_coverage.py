"""Offline language coverage, not translation quality or training admission."""
from .source_answer_eval import evaluate_source_answers

# Stable public buckets avoid echoing arbitrary source-language metadata.
LANGUAGES = ('en', 'gu', 'hi', 'pra', 'other', 'mixed', 'none', 'undeclared')


def _bucket(evidence):
    if not evidence:
        return 'none'
    declared = {entry.get('language') for entry in evidence}
    if len(declared) != 1:
        return 'mixed'
    value = next(iter(declared))
    if value is None:
        return 'undeclared'
    if value in ('pra', 'pra-Deva', 'pra-Latn'):
        return 'pra'
    return value if value in ('en', 'gu', 'hi') else 'other'


def evaluate_source_language_coverage(cases, outputs, reviews=None):
    """Preserve missing outputs in per-source-language denominators.

    Language declarations are not independently detected or authenticated.
    This does not infer answer language, translation accuracy or entailment.
    All input validation and exact-output review binding precede aggregation.
    """
    report = evaluate_source_answers(cases, outputs, reviews)
    groups = {language: {'case_count': 0, 'output_count': 0,
                        'mechanically_accepted': 0, 'citation_requirement_met': 0,
                        'review_count': 0, 'supported_annotations': 0}
              for language in LANGUAGES}
    for case, row in zip(cases, report['cases']):
        group = groups[_bucket(case['evidence'])]
        group['case_count'] += 1
        group['output_count'] += row['mechanical'] != 'missing'
        group['mechanically_accepted'] += row['mechanical'] == 'accepted'
        group['citation_requirement_met'] += row['citation_requirement_met']
        group['review_count'] += row['human_verdict'] is not None
        group['supported_annotations'] += row['human_verdict'] == 'supported'
    return {'source_language_groups': groups, 'case_count': report['case_count'],
            'source_languages_verified': False, 'translation_quality_verified': False,
            'semantic_quality_verified': False, 'runtime_admitted': False,
            'scope': 'Declared source-language coverage only; no model, translation or training admission.'}
