"""Replay now-disclosed first-evaluation artifacts, not a new unseen trial."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_claim_support as evaluator
import predict_controlled_support as candidate


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class ControlledSupportChallengeTests(unittest.TestCase):
    def setUp(self):
        self.observed=json.loads((ROOT/'evals/controlled_support_observed.json').read_text())
        self.data,self.data_sha=evaluator.read_json(ROOT/'evals/controlled_support_cases.json')
        self.inputs=evaluator.candidate_inputs(self.data,self.data_sha)

    def test_frozen_component_hashes_and_fixture_shape(self):
        o=self.observed
        self.assertEqual(o['candidate_source_sha256'],sha(ROOT/'scripts/predict_controlled_support.py'))
        self.assertEqual(o['evaluator_source_sha256'],sha(ROOT/'scripts/evaluate_claim_support.py'))
        self.assertEqual(o['fixture_sha256'],self.data_sha)
        self.assertEqual(o['controls_sha256'],sha(ROOT/'evals/controlled_support_controls.json'))
        self.assertEqual(len(self.data['cases']),48)
        self.assertEqual(len({c['group_id'] for c in self.data['cases']}),16)
        self.assertEqual({c['phenomenon'] for c in self.data['cases']},{'negation','quantifiers','conditionals','cross_source'})
        for label in evaluator.LABELS:self.assertEqual(sum(c['label']==label for c in self.data['cases']),16)
        for c in self.inputs['cases']:self.assertEqual(set(c),{'id','passages','claim','citations'})

    def test_first_evaluation_predictions_and_scoring_reproduce(self):
        predictions,trace=candidate.run(self.inputs)
        score=evaluator.score(self.data,self.data_sha,predictions)
        self.assertEqual(predictions['predictions'],self.observed['fresh_predictions'])
        self.assertEqual(score['observations'],self.observed['fresh_observations'])
        self.assertEqual(score['confusion'],self.observed['fresh_confusion'])
        self.assertEqual(trace['prediction_sha256'],self.observed['fresh_prediction_sha256'])
        self.assertEqual(trace['input_sha256'],self.observed['fresh_input_sha256'])
        self.assertEqual(score['observations']['correct_predictions'],48)
        self.assertEqual(score['observations']['complete_matched_groups_correct'],16)
        self.assertEqual(score['observations']['unsupported_as_supported'],0)

    def test_disclosed_inconsistent_and_unsupported_controls_reproduce(self):
        p=ROOT/'evals/controlled_support_controls.json';controls=json.loads(p.read_text())
        self.assertEqual(len(controls),12)
        value={'protocol':1,'dataset_sha256':sha(p),'cases':[row['case'] for row in controls]}
        value['input_sha256']=hashlib.sha256(evaluator.canonical_bytes(value)).hexdigest()
        predictions,trace=candidate.run(value)
        expected={row['case']['id']:row['expected_label'] for row in controls}
        self.assertEqual({p['case_id']:p['label'] for p in predictions['predictions']},expected)
        summary=[{key:r[key] for key in ('case_id','label','reason')} for r in trace['cases']]
        self.assertEqual(summary,self.observed['controls'])
        self.assertEqual(sum(r['reason']=='inconsistent_context' for r in summary),6)
        self.assertEqual(sum(r['reason'].startswith('unsupported_') for r in summary),6)

    def test_broader_disclosed_english_zero_coverage_remains_explicit(self):
        data,digest=evaluator.read_json(ROOT/'evals/claim_support_cases.json')
        self.assertEqual(digest,self.observed['broader_disclosed_fixture_sha256'])
        inputs=evaluator.candidate_inputs(data,digest)
        predictions,_=candidate.run(inputs)
        score=evaluator.score(data,digest,predictions)
        self.assertEqual(score['observations'],self.observed['broader_disclosed_observations'])
        self.assertEqual(score['observations']['semantic_predictions'],0)
        self.assertEqual(score['observations']['abstentions'],48)
        self.assertIsNone(score['observations']['accuracy_when_predicted'])


if __name__=='__main__':unittest.main()
