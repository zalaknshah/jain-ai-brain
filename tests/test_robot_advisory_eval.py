import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from robot_advisory_eval import validate_cases, collect_local, summarize

CASES = json.loads((Path(__file__).resolve().parents[1] / 'evals/robot_advisory/cases.json').read_text(encoding='utf-8'))

class RobotAdvisoryEvalTests(unittest.TestCase):
    def test_parallel_case_matrix(self):
        self.assertEqual(len(validate_cases(CASES)),18)
        self.assertEqual(len({c['scenario'] for c in CASES}),6)
    def test_missing_outputs_remain_unreviewed(self):
        r=summarize(CASES,{})
        self.assertEqual(len(r['missing_output_ids']),18)
        self.assertFalse(r['semantic_quality_verified'])
        self.assertFalse(r['robot_control_authorized'])
    def test_case_output_and_rubric_binding(self):
        c=CASES[:3]; value={'response':'Synthetic answer','lexical_allowed':True,'action_proposed':False}
        a=summarize(c,{c[0]['id']:value})['cases'][0]['review_binding_sha256']
        changed=copy.deepcopy(c)
        for row in changed:row['rubric']+=' Changed'
        self.assertNotEqual(a,summarize(changed,{c[0]['id']:value})['cases'][0]['review_binding_sha256'])
        self.assertNotEqual(a,summarize(c,{c[0]['id']:{**value,'response':'Changed'}})['cases'][0]['review_binding_sha256'])
    def test_reject_invalid_matrices(self):
        bad=[]
        bad.append(CASES[:-1]);bad.append(CASES+[CASES[0]])
        for key,value in [('id','wrong'),('language','fr'),('prompt',''),('rubric','different'),('extra',True)]:
            c=copy.deepcopy(CASES);c[0][key]=value;bad.append(c)
        for c in bad:
            with self.subTest(c=c[0] if c else None),self.assertRaises(ValueError):validate_cases(c)
    def test_reject_unknown_or_invalid_outputs(self):
        for outputs in [{'unknown':{}},{CASES[0]['id']:None},{CASES[0]['id']:{'response':'x','lexical_allowed':1,'action_proposed':False}}]:
            with self.assertRaises(ValueError):summarize(CASES,outputs)
    def test_local_collection_no_network_or_external_reasoner(self):
        # Requests/sockets and environment-selected reasoners must not be involved.
        with patch('socket.socket',side_effect=AssertionError('network used')),patch('jace.engine.configured_reasoner',side_effect=AssertionError('configured model used')):
            outputs=collect_local(CASES)
        self.assertEqual(len(outputs),18)
        report=summarize(CASES,outputs)
        self.assertEqual(report['output_count'],18)
        self.assertTrue(all(r['human_review']=='not_performed' for r in report['cases']))
        self.assertFalse(report['semantic_quality_verified'])
    def test_cli_is_portable_to_ascii_stdout(self):
        import os
        import subprocess
        root=Path(__file__).resolve().parents[1]
        run=subprocess.run([sys.executable,str(root/'scripts/evaluate_robot_advisory.py')],
                           cwd=root,env={**os.environ,'PYTHONIOENCODING':'ascii'},
                           capture_output=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stderr.decode('ascii',errors='replace'))
        result=json.loads(run.stdout.decode('ascii'))
        self.assertEqual(result['report']['output_count'],18)
        self.assertTrue(any('આ' in v['response'] for v in result['outputs'].values()))
    def test_summary_does_not_disclose_answer_text(self):
        outputs={CASES[0]['id']:{'response':'distinctive-synthetic-answer','lexical_allowed':False,'action_proposed':False}}
        self.assertNotIn('distinctive-synthetic-answer',json.dumps(summarize(CASES,outputs)))

if __name__=='__main__':unittest.main()
