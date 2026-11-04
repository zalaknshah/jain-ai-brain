"""Original synthetic retrieval labels, not a scholarly/model-quality benchmark."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner


def ranking_metrics(retrieved: list, relevant: list, k: int = 5) -> dict:
    """Distinct IDs, recall and reciprocal first relevant rank at fixed k.

    Empty-label queries are reported separately, never averaged as perfect recall.
    """
    if type(k) is not int or not 1 <= k <= 100 or len(set(retrieved)) != len(retrieved) or len(set(relevant)) != len(relevant):
        raise ValueError('metrics require unique IDs and a bounded positive integer k')
    selected = retrieved[:k]
    hits = [index + 1 for index, value in enumerate(selected) if value in relevant]
    return {'recall_at_k': len(hits) / len(relevant) if relevant else None,
            'reciprocal_rank_at_k': 1 / hits[0] if hits else (0.0 if relevant else None),
            'unlabeled_returned_at_k': len(selected) - len(hits),
            'empty_label_correct': not selected if not relevant else None}


def run() -> dict:
    cases = json.loads((ROOT / 'evals/retrieval/cases.json').read_text())
    if not isinstance(cases, list) or len(cases) > 100 or any(
            len(case.get('memories', [])) > 100 or type(case.get('newer_noise_count', 0)) is not int
            or not 0 <= case.get('newer_noise_count', 0) <= 200 for case in cases):
        raise ValueError('synthetic evaluation fixture exceeds work limits')
    outcomes = []
    with tempfile.TemporaryDirectory(prefix='jace-retrieval-eval-') as directory:
        for index, case in enumerate(cases):
            engine = CognitiveEngine(Path(directory)/f'{index}.db', ROOT/'evals/retrieval/corpus.json', LocalReasoner())
            ids = {}
            try:
                for record in case.get('memories', []):
                    item, _ = engine.remember(record.get('owner', 'fixture-user'), record['text'],
                        memory_scope=record.get('scope', 'default'), expires_at=record.get('expires_at'))
                    if item is None:
                        raise ValueError('synthetic memory fixture was rejected')
                    ids[record['label']] = item.memory_id
                for number in range(case.get('newer_noise_count', 0)):
                    engine.remember('fixture-user', f'I prefer quiet music number {number}.')
                result = engine.think('fixture-user', case['query'], memory_scope=case.get('scope', 'default'))
                memory_ids = [item.memory_id for item in result.memories_used]
                expected = [ids[label] for label in case.get('relevant_memories', [])]
                source_ids = [item.entry_id for item in result.canonical_evidence]
                memory_metrics = ranking_metrics(memory_ids, expected)
                source_metrics = ranking_metrics(source_ids, case.get('relevant_sources', []))
                expected_first = ids.get(case.get('first_memory'))
                passed = all(value['recall_at_k'] in (None, 1.0) and value['empty_label_correct'] is not False
                             and value['unlabeled_returned_at_k'] == 0 for value in (memory_metrics, source_metrics))
                passed = passed and (expected_first is None or memory_ids[:1] == [expected_first])
                outcomes.append({'id': case['id'], 'passed': passed, 'memory': memory_metrics,
                                 'source': source_metrics, 'selected_memory_labels': [{value: label for label, value in ids.items()}.get(item, 'synthetic-noise') for item in memory_ids],
                                 'selected_source_ids': source_ids})
            finally:
                engine.close()
    aggregates = {}
    for kind in ('memory', 'source'):
        positive = [case[kind] for case in outcomes if case[kind]['recall_at_k'] is not None]
        negative = [case[kind] for case in outcomes if case[kind]['empty_label_correct'] is not None]
        aggregates[kind] = {'positive_queries': len(positive), 'empty_label_queries': len(negative),
            'mean_recall_at_5': sum(item['recall_at_k'] for item in positive)/len(positive) if positive else None,
            'mean_reciprocal_rank_at_5': sum(item['reciprocal_rank_at_k'] for item in positive)/len(positive) if positive else None,
            'empty_label_correct': sum(item['empty_label_correct'] for item in negative),
            'unlabeled_returns': sum(case[kind]['unlabeled_returned_at_k'] for case in outcomes)}
    return {'passed': all(case['passed'] for case in outcomes), 'case_count': len(outcomes),
            'aggregate': aggregates, 'cases': outcomes,
            'scope': 'Original fictional fixtures, exact lexical/ranking and isolation checks only. No model calls, sacred texts, held-out semantic quality or scholarly grounding validation.'}


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
