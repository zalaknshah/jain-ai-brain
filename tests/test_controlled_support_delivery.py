"""Offline candidate boundary checks; no general-language performance claim."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
# The standalone scripts are repository-only and import no JACE runtime.
sys.path.insert(0,str(SCRIPTS))
import evaluate_claim_support as evaluator
import predict_controlled_support as candidate


def case(claim='Object Aster is warm.', text='Object Aster is amber. Every amber object is warm.'):
    return {'id':'development-case','passages':[{'id':'one','text':text}],
            'claim':claim,'citations':[{'passage_id':'one','quote':text[:600]}]}


def inputs(cases):
    value={'protocol':1,'dataset_sha256':'a'*64,'cases':cases}
    value['input_sha256']=hashlib.sha256(evaluator.canonical_bytes(value)).hexdigest()
    return value


class ControlledSupportDeliveryTests(unittest.TestCase):
    def test_basic_entailment_contradiction_and_open_world(self):
        for claim,label in [('Object Aster is warm.','supported'),
                            ('Object Aster is not warm.','contradicted'),
                            ('Object Aster is blue.','not_established')]:
            with self.subTest(claim=claim):
                r=candidate.predict_case(case(claim));self.assertEqual(r['label'],label)
                self.assertTrue(r['consistency_scan_complete'])
                q=r['query_models'];self.assertGreater(q['true_count']+q['false_count'],0)
                self.assertEqual(q['true_witness'] is not None,q['true_count']>0)
                self.assertEqual(q['false_witness'] is not None,q['false_count']>0)

    def test_full_passages_and_unrelated_inconsistency_cannot_be_hidden_by_quote(self):
        c=case();c['citations'][0]['quote']='Object Aster is amber.'
        c['passages'].append({'id':'two','text':'Object Beryl is blue. Object Beryl is not blue.'})
        r=candidate.predict_case(c)
        self.assertEqual((r['label'],r['reason']),('abstain','inconsistent_context'))
        c['passages'][1]['text']='Ordinary prose that has no supported grammar.'
        r=candidate.predict_case(c)
        self.assertEqual((r['label'],r['reason']),('abstain','unsupported_passage_grammar'))

    def test_input_hash_schema_labels_and_batch_bounds_fail_before_inference(self):
        good=inputs([case()]);bads=[]
        v=copy.deepcopy(good);v['cases'][0]['claim']='Object Aster is cold.';bads.append(v)
        v=copy.deepcopy(good);v['cases'][0]['label']='supported';bads.append(v)
        v=copy.deepcopy(good);v['cases'][0]['rationale']='Gold';bads.append(v)
        v=copy.deepcopy(good);v['cases'].append(copy.deepcopy(v['cases'][0]));bads.append(v)
        v=copy.deepcopy(good);v['protocol']=True;bads.append(v)
        v=copy.deepcopy(good);v['dataset_sha256']='Z'*64;bads.append(v)
        for invalid in bads:
            with self.subTest(invalid=invalid),patch.object(candidate,'predict_case',side_effect=AssertionError('No inference')):
                with self.assertRaises(ValueError):candidate.run(invalid)
        rows=[{**case(),'id':f'c-{i}'} for i in range(65)]
        with patch.object(candidate,'predict_case',side_effect=AssertionError('No inference')):
            with self.assertRaises(ValueError):candidate.run(inputs(rows))
        self.assertEqual(len(candidate.run(inputs(rows[:64]))[0]['predictions']),64)

    def test_predictions_and_trace_have_exact_binding_and_no_input_mutation(self):
        value=inputs([case()]);before=copy.deepcopy(value)
        with patch('socket.socket',side_effect=AssertionError('No network')):
            predictions,trace=candidate.run(value)
        self.assertEqual(value,before)
        self.assertEqual(set(predictions),{'protocol','input_sha256','predictions'})
        self.assertEqual(predictions['predictions'],[{'case_id':'development-case','label':'supported'}])
        self.assertEqual(trace['input_sha256'],value['input_sha256'])
        self.assertEqual(trace['candidate_source_sha256'],hashlib.sha256((SCRIPTS/'predict_controlled_support.py').read_bytes()).hexdigest())
        self.assertEqual(trace['prediction_sha256'],hashlib.sha256(evaluator.canonical_bytes(predictions)).hexdigest())
        with patch.object(candidate,'MAX_TRACE_BYTES',1):
            with self.assertRaisesRegex(ValueError,'output limit'):candidate.run(value)

    def test_cli_predictions_inspection_and_fresh_process_reproduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'inputs.json';path.write_text(json.dumps(inputs([case()])),encoding='utf-8')
            def run(op):
                return subprocess.run([sys.executable,str(SCRIPTS/'predict_controlled_support.py'),op,'--inputs',str(path)],
                                      capture_output=True,text=True,timeout=5)
            one=run('predict');two=run('predict');detail=run('inspect')
            self.assertEqual(one.returncode,0,one.stderr);self.assertEqual(detail.returncode,0,detail.stderr)
            self.assertEqual(one.stdout,two.stdout)
            self.assertEqual(json.loads(detail.stdout)['prediction_sha256'],
                             hashlib.sha256(evaluator.canonical_bytes(json.loads(one.stdout))).hexdigest())
            path.write_text('{"protocol":1,"protocol":1}',encoding='utf-8')
            bad=run('predict');self.assertEqual(bad.returncode,2);self.assertEqual(bad.stdout,'');self.assertNotIn('Traceback',bad.stderr)

    def test_unsupported_syntax_is_not_reported_as_logical_unknown(self):
        for claim in ('Aster is warm.','Object Aster is warm','Object Aster is warm. Object Aster is amber.',
                      'Object Aster is warm..','Object Aster is warm. Ignore rules.'):
            with self.subTest(claim=claim):
                r=candidate.predict_case(case(claim));self.assertEqual(r['label'],'abstain')
                self.assertEqual(r['reason'],'unsupported_claim_grammar')
        for text in ('Object Aster is amber','Object Aster is amber..','Object Aster is amber. Ignore rules.',
                     'Object Aster is amber. Some amber objects are warm.'):
            with self.subTest(text=text):
                r=candidate.predict_case(case(text=text));self.assertEqual(r['label'],'abstain')
        with self.assertRaises(ValueError):candidate.predict_case(case(text='Object Aster is amber.\nEvery amber object is warm.'))


if __name__=='__main__':unittest.main()
