"""Observe citation matching on authored fiction; no semantic pass/accuracy score.

This deliberately keeps accepted unsupported answers visible. A successful
diagnostic execution does not mean source support was checked or established.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.models import CanonicalEntry
from jace.model_output import check_model_output


def run() -> dict:
    fixture_path = ROOT / 'evals' / 'semantic_support_cases.json'
    raw = fixture_path.read_bytes()
    fixtures = json.loads(raw)
    results = []
    for case in fixtures['cases']:
        records = [CanonicalEntry(**record) for record in case['records']]
        row = {'id': case['id'], 'feature': case['feature'],
               'author_semantic_label': case['semantic_label'], 'rationale': case['rationale'],
               'input_answer': case['content']['answer'],
               'input_citations': case['content']['citations']}
        try:
            checked = check_model_output(json.dumps(case['content'], ensure_ascii=False), records)
            row.update(mechanically_accepted=True, actual_answer=checked.answer,
                       actual_citations=[{'entry_id': item.entry.entry_id, 'quote': item.quote}
                                         for item in checked.citations],
                       actual_rendered_output=checked.render())
        except ValueError as error:
            row.update(mechanically_accepted=False, actual_error=str(error))
        results.append(row)
    counts = Counter(row['author_semantic_label'] for row in results)
    accepted = Counter(row['author_semantic_label'] for row in results if row['mechanically_accepted'])
    return {
        'scope': 'Original fictional English diagnostic of exact citation matching, not a model, semantic accuracy or doctrinal benchmark.',
        'fixture_sha256': hashlib.sha256(raw).hexdigest(),
        'label_policy': fixtures['label_policy'],
        'label_origin': 'Fixture-author judgments, reviewed as fictional examples; not labels produced by the validator.',
        'semantic_labels_produced_by_system': False,
        'observations': {
            'case_count': len(results),
            'author_label_counts': dict(counts),
            'mechanically_accepted_by_author_label': {label: accepted[label] for label in counts},
            'mechanically_accepted_total': sum(row['mechanically_accepted'] for row in results),
            'mechanically_accepted_without_source_support': sum(
                row['mechanically_accepted'] and row['author_semantic_label'] != 'supported' for row in results),
        },
        'cases': results,
        'limits': [
            'Exact IDs and substrings do not establish that a passage entails an answer; full context may contradict an isolated exact quote.',
            'Labels assume the explicitly stipulated fictional passages, not the truth of real-world sources. Unknown facts are not assumed false.',
            'This small hand-authored set is not representative, an unseen holdout, or a calibrated measure of reasoning quality.',
            'No model/provider is called and no religious source is acquired, admitted, trained on or qualified.',
            'The process exit status reports diagnostic execution only. There is no semantic pass/accuracy score.',
        ],
    }


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
