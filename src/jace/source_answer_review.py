"""Incomplete review drafts for saved answers; never human review or approval."""
from __future__ import annotations

from .source_answer_eval import evaluate_source_answers


def prepare_answer_review(cases, outputs, reviews=None) -> dict:
    """Bind blank drafts using the unchanged evaluator; do not infer verdicts.

    Existing reviews must validate before they are omitted from pending work.
    Missing outputs are listed separately and receive no review draft. IDs and
    hashes may reveal information and must not be treated as anonymized data.
    """
    report = evaluate_source_answers(cases, outputs, reviews)
    drafts = {}
    missing, reviewed = [], []
    for case in report['cases']:
        case_id = case['id']
        if case['mechanical'] == 'missing':
            missing.append(case_id)
        elif case['human_verdict'] is not None:
            reviewed.append(case_id)
        else:
            drafts[case_id] = {
                'review_binding_sha256': case['review_binding_sha256'],
                'verdict': None,
                'reviewer': '',
                'rationale': '',
            }
    return {
        'draft_reviews': drafts,
        'missing_output_case_ids': missing,
        'already_reviewed_case_ids': reviewed,
        'draft_count': len(drafts),
        'semantic_quality_verified': False,
        'runtime_admitted': False,
        'scope': ('Incomplete drafts only. Inspect the exact saved question, sources and answer privately. '
                  'Fill a verdict, reviewer label and rationale manually; blank drafts are not valid reviews. '
                  'Mechanical citation acceptance is not semantic support. Existing review labels are '
                  'unverified assertions, not proof of qualified human review. No source, training or runtime admission.'),
    }
