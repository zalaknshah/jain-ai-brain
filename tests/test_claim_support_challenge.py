"""Disclosed challenge transport checks, not runtime semantic accuracy."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/evaluate_claim_support.py'
spec = importlib.util.spec_from_file_location('challenge_evaluator', SCRIPT)
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


class ClaimSupportChallengeTests(unittest.TestCase):
    def setUp(self):
        self.data, self.sha = e.read_json(ROOT/'evals/claim_support_cases.json')
        self.inputs = e.candidate_inputs(self.data, self.sha)

    def test_complete_matched_challenge_has_eight_phenomena_and_equal_labels(self):
        self.assertEqual(len(self.data['cases']), 48)
        self.assertEqual(len({c['group_id'] for c in self.data['cases']}), 16)
        for phenomenon in e.PHENOMENA:
            self.assertEqual(sum(c['phenomenon']==phenomenon for c in self.data['cases']), 6)
        for label in e.LABELS:
            self.assertEqual(sum(c['label']==label for c in self.data['cases']), 16)
        self.assertEqual({c['id'] for c in self.data['cases']}, {c['id'] for c in self.inputs['cases']})
        for c in self.inputs['cases']:
            self.assertEqual(set(c), {'id','passages','claim','citations'})

    def test_abstention_and_trivial_support_are_reported_without_false_pass(self):
        absent = e.score(self.data,self.sha,e.baseline_predictions(self.inputs,'abstain'))
        yes = e.score(self.data,self.sha,e.baseline_predictions(self.inputs,'supported'))
        a,b = absent['observations'],yes['observations']
        self.assertEqual((a['cases'],a['semantic_predictions'],a['abstentions'],a['correct_predictions']), (48,0,48,0))
        self.assertIsNone(a['accuracy_when_predicted']); self.assertEqual(a['supported_recall'],0)
        self.assertEqual((b['semantic_predictions'],b['correct_predictions'],b['unsupported_as_supported'],b['unsupported_case_count']), (48,16,32,32))
        for report in (absent,yes):
            self.assertEqual(report['observations']['complete_matched_groups_correct'],0)
            self.assertNotIn('passed',report)
            for original,observed in zip(self.data['cases'],report['cases']):
                self.assertTrue(all(observed[k]==v for k,v in original.items()))

    def test_reordering_predictions_does_not_change_case_binding(self):
        predictions=e.baseline_predictions(self.inputs,'abstain')
        predictions['predictions'][0]['label']='contradicted'
        initial=e.score(self.data,self.sha,predictions)
        predictions['predictions'].reverse()
        reordered=e.score(self.data,self.sha,predictions)
        for key in ('cases','groups','observations','confusion'):
            self.assertEqual(initial[key],reordered[key])
        self.assertNotEqual(initial['prediction_sha256'],reordered['prediction_sha256'])

    def test_cli_outputs_reproduce_in_fresh_process_without_runtime_environment(self):
        import os
        env=dict(os.environ,JACE_LLM_URL='https://unreachable.invalid/never',JACE_CANONICAL_PATH='/missing/never')
        def run(*args):
            return subprocess.run([sys.executable,str(SCRIPT),*args],env=env,capture_output=True,text=True,timeout=5)
        first=run('export');second=run('export')
        self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(first.stdout,second.stdout)
        self.assertEqual(json.loads(first.stdout),self.inputs)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'predictions.json';p.write_text(run('baseline','--baseline','abstain').stdout,encoding='utf-8')
            one=run('score','--predictions',str(p));two=run('score','--predictions',str(p))
            self.assertEqual(one.returncode,0,one.stderr);self.assertEqual(one.stdout,two.stdout)
            report=json.loads(one.stdout)
            self.assertEqual(report['prediction_file_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(report['observations']['semantic_predictions'],0)

    def test_even_gold_only_revision_invalidates_previous_prediction_binding(self):
        predictions=e.baseline_predictions(self.inputs,'abstain')
        changed=copy.deepcopy(self.data)
        changed['cases'][0]['rationale']+=' Additional review clarification.'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'cases.json';p.write_text(json.dumps(changed),encoding='utf-8')
            data,sha=e.read_json(p)
            with self.assertRaisesRegex(ValueError,'input hash'):
                e.score(data,sha,predictions)


if __name__=='__main__': unittest.main()
