import copy
import importlib.util
import io
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jace.source_answer_eval import evaluate_source_answers
from jace.source_answer_review import prepare_answer_review

ROOT=Path(__file__).resolve().parents[1]


class AnswerReviewDraftTests(unittest.TestCase):
    def setUp(self):
        self.case={'id':'fixture','question':'Private synthetic question?', 'require_citation':True,
            'evidence':[dict(entry_id='source',title='Private title',principle='Wait for permission.',
                            guidance='Private guidance',source='Private source',language='en',verified=True)]}
        self.output=json.dumps({'answer':'Proceed now.', 'citations':[{'entry_id':'source','quote':'Wait for permission.'}]})
        self.outputs={'fixture':self.output}

    def test_draft_uses_exact_binding_but_no_inferred_verdict(self):
        before=copy.deepcopy((self.case,self.outputs))
        report=prepare_answer_review([self.case],self.outputs)
        draft=report['draft_reviews']['fixture']
        expected=evaluate_source_answers([self.case],self.outputs)['cases'][0]['review_binding_sha256']
        self.assertEqual(draft,dict(review_binding_sha256=expected,verdict=None,reviewer='',rationale=''))
        self.assertFalse(report['semantic_quality_verified']);self.assertFalse(report['runtime_admitted'])
        self.assertEqual((self.case,self.outputs),before)
        with self.assertRaises(ValueError): evaluate_source_answers([self.case],self.outputs,report['draft_reviews'])

    def test_filled_draft_can_be_used_without_granting_authority(self):
        draft=prepare_answer_review([self.case],self.outputs)['draft_reviews']
        draft['fixture'].update(verdict='unsupported',reviewer='Synthetic test label',rationale='Test contradiction.')
        report=evaluate_source_answers([self.case],self.outputs,draft)
        self.assertEqual(report['human_verdict_counts']['unsupported'],1)
        self.assertFalse(report['semantic_quality_verified']);self.assertFalse(report['runtime_admitted'])
        pending=prepare_answer_review([self.case],self.outputs,draft)
        self.assertEqual(pending['draft_reviews'],{})
        self.assertEqual(pending['already_reviewed_case_ids'],['fixture'])
        self.assertNotIn('Synthetic test label',json.dumps(pending))

    def test_missing_outputs_do_not_get_drafts(self):
        report=prepare_answer_review([self.case],{})
        self.assertEqual(report['draft_count'],0)
        self.assertEqual(report['missing_output_case_ids'],['fixture'])
        self.assertEqual(report['already_reviewed_case_ids'],[])

    def test_rejected_mechanical_output_still_needs_human_review(self):
        report=prepare_answer_review([self.case],{'fixture':'not JSON'})
        self.assertEqual(report['draft_count'],1)
        self.assertIsNone(report['draft_reviews']['fixture']['verdict'])

    def test_output_omits_sources_question_and_answer(self):
        text=json.dumps(prepare_answer_review([self.case],self.outputs))
        for private in ('Private synthetic question','Private title','Wait for permission','Proceed now','Private source'):
            self.assertNotIn(private,text)

    def test_stale_or_malformed_existing_reviews_fail_closed(self):
        draft=prepare_answer_review([self.case],self.outputs)['draft_reviews']
        draft['fixture'].update(verdict='uncertain',reviewer='Fixture',rationale='Fixture review')
        for field in ('question','require_citation'):
            case=copy.deepcopy(self.case);case[field]='Changed' if field=='question' else False
            with self.assertRaises(ValueError):prepare_answer_review([case],self.outputs,draft)
        with self.assertRaises(ValueError):prepare_answer_review([self.case],{'fixture':self.output+' '},draft)
        draft['fixture']['reviewer']=''
        with self.assertRaises(ValueError):prepare_answer_review([self.case],self.outputs,draft)

    def test_existing_case_and_output_bounds_apply(self):
        for cases,outputs in [([],{}),([self.case]*257,{}),([self.case,self.case],{}),
                              ([self.case],{'unknown':'x'}),([self.case],{'fixture':None})]:
            with self.assertRaises(ValueError): prepare_answer_review(cases,outputs)

    def test_real_cli_disclosure_and_no_input_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'evaluation.json';path.write_text(json.dumps({'cases':[self.case],'outputs':self.outputs}))
            before=path.read_bytes();command=[sys.executable,str(ROOT/'scripts/prepare_answer_review.py'),str(path)]
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1',JACE_LLM_URL='invalid-never-load',JACE_DB_PATH=directory+'/never.sqlite')
            denied=subprocess.run(command,capture_output=True,env=env,timeout=15)
            self.assertEqual(denied.returncode,2);self.assertEqual(denied.stdout,b'')
            run=subprocess.run(command+['--allow-local-disclosure'],capture_output=True,env=env,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads(run.stdout)['draft_count'],1)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual([p.name for p in Path(directory).iterdir()],['evaluation.json'])
            link=Path(directory)/'link.json';link.symlink_to(path)
            run=subprocess.run([*command[:-1],str(link),'--allow-local-disclosure'],capture_output=True,env=env,timeout=15)
            self.assertEqual(run.returncode,2);self.assertEqual(run.stdout,b'')
            self.assertNotIn(str(path).encode(),run.stderr)

    def test_cli_output_io_is_sanitized(self):
        spec=importlib.util.spec_from_file_location('answer_draft_cli',ROOT/'scripts/prepare_answer_review.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        class BadOutput(io.StringIO):
            def write(self,text):
                super().write(text[:5]);raise OSError('private-path /hidden/output')
        out=BadOutput();err=io.StringIO()
        with patch('sys.argv',['draft','/unused','--allow-local-disclosure']), \
             patch.object(module,'read_regular',return_value=json.dumps({'cases':[self.case],'outputs':self.outputs})), \
             contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as stop:module.main()
        self.assertEqual(stop.exception.code,2);self.assertTrue(out.getvalue())
        self.assertIn('output may be incomplete',err.getvalue());self.assertNotIn('/hidden',err.getvalue())

if __name__ == '__main__':unittest.main()
