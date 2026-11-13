import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from jace.source_answer_eval import evaluate_source_answers


class SourceAnswerEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.source = {'entry_id':'synthetic', 'title':'Example', 'principle':'Wait for confirmation.',
                       'guidance':'Synthetic guidance.', 'source':'Original synthetic fixture',
                       'work':'Fixture', 'language':'en', 'location':'line 1', 'license':'MIT', 'verified':True}
        self.case = {'id':'one', 'question':'What next?', 'require_citation':True, 'evidence':[self.source]}
        self.answer = json.dumps({'answer':'Proceed without confirmation.',
            'citations':[{'entry_id':'synthetic','quote':'Wait for confirmation.'}]})

    def run_case(self, cases=None, outputs=None, reviews=None):
        return evaluate_source_answers(cases or [self.case], {'one':self.answer} if outputs is None else outputs, reviews)

    def review(self, verdict='unsupported'):
        binding = self.run_case()['cases'][0]['review_binding_sha256']
        return {'one': {'review_binding_sha256':binding, 'reviewer':'synthetic-test-reviewer',
                        'verdict':verdict, 'rationale':'The answer contradicts the quoted sentence.'}}

    def test_exact_citation_does_not_become_semantic_pass(self):
        r = self.run_case()
        self.assertEqual(r['mechanically_accepted'], 1)
        self.assertEqual(r['review_count'], 0)
        self.assertFalse(r['semantic_quality_verified'])
        r = self.run_case(reviews=self.review())
        self.assertEqual(r['human_verdict_counts']['unsupported'], 1)
        self.assertFalse(r['semantic_quality_verified'])
        self.assertFalse(r['runtime_admitted'])

    def test_missing_outputs_and_reviews_stay_in_denominator(self):
        two = dict(self.case, id='two')
        r = self.run_case(cases=[self.case,two])
        self.assertEqual((r['case_count'],r['output_count'],r['unreviewed_count']), (2,1,2))
        self.assertEqual(r['cases'][1]['mechanical'], 'missing')
        self.assertFalse(r['complete_output_coverage'])

    def test_uncited_answer_separate_from_mechanical_check(self):
        raw = json.dumps({'answer':'Unsourced.', 'citations':[]})
        r = self.run_case(outputs={'one':raw})
        self.assertEqual(r['mechanically_accepted'],1)
        self.assertEqual(r['citation_requirement_met'],0)
        self.case['require_citation'] = False
        self.assertEqual(self.run_case(outputs={'one':raw})['citation_requirement_met'],1)

    def test_invalid_citations_and_unreviewed_sources_rejected(self):
        for raw in ('bad JSON', self.answer.replace('synthetic"','unknown"'), self.answer.replace('Wait for','Never seek')):
            self.assertEqual(self.run_case(outputs={'one':raw})['mechanically_accepted'],0)
        self.source['verified'] = False
        self.assertEqual(self.run_case()['mechanically_accepted'],0)

    def test_stale_review_after_any_case_or_output_change(self):
        reviews = self.review()
        for name, value in [('question','Different?'),('require_citation',False)]:
            changed = dict(self.case, **{name:value})
            with self.assertRaises(ValueError): self.run_case(cases=[changed],reviews=reviews)
        changed = copy.deepcopy(self.case); changed['evidence'][0]['location']='line 2'
        with self.assertRaises(ValueError): self.run_case(cases=[changed], reviews=reviews)
        with self.assertRaises(ValueError): self.run_case(outputs={'one':self.answer+' '},reviews=reviews)
        with self.assertRaises(ValueError): self.run_case(outputs={},reviews=reviews)

    def test_human_supported_annotation_is_not_verified_quality(self):
        r = self.run_case(reviews=self.review('supported'))
        self.assertTrue(r['complete_review_coverage'])
        self.assertFalse(r['semantic_quality_verified'])

    def test_report_omits_source_answer_question_and_reviewer_text(self):
        raw = json.dumps(self.run_case(reviews=self.review()))
        for sensitive in ('What next?', 'Wait for confirmation.', 'Proceed without', 'synthetic-test-reviewer'):
            self.assertNotIn(sensitive,raw)

    def test_unknown_ids_duplicate_cases_and_null_output_rejected(self):
        for cases,outputs,reviews in [([self.case,self.case],{},{}),([self.case],{'bad':'x'},{}),
                                      ([self.case],{}, {'bad':{}}),([self.case],{'one':None},{})]:
            with self.assertRaises(ValueError): evaluate_source_answers(cases,outputs,reviews)

    def test_malformed_review_rejected(self):
        for key,value in [('verdict','pass'),('reviewer',''),('rationale',''),('review_binding_sha256','0'*64)]:
            r=self.review();r['one'][key]=value
            with self.assertRaises(ValueError): self.run_case(reviews=r)

    def test_source_types_and_bounds_rejected(self):
        for key,value in [('entry_id',[]),('verified',1),('source_byte_start',True),('principle','x'*40001)]:
            changed=copy.deepcopy(self.case);changed['evidence'][0][key]=value
            with self.assertRaises(ValueError): self.run_case(cases=[changed])
        with self.assertRaises(ValueError): evaluate_source_answers([],{})
        with self.assertRaises(ValueError): evaluate_source_answers([self.case]*257,{})

    def test_unicode_and_crlf_excerpts_keep_mechanical_contract(self):
        for passage in ('पहले जाँच करें।', 'પહેલાં તપાસ કરો.', 'First line.\r\nSecond line.'):
            self.source['principle'] = passage
            raw = json.dumps({'answer':'Synthetic response only.', 'citations':[
                {'entry_id':'synthetic', 'quote':passage}]},ensure_ascii=False)
            self.assertEqual(self.run_case(outputs={'one':raw})['mechanically_accepted'],1)

    def test_cli_inspects_without_source_text_output(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.json';p.write_text(json.dumps({'cases':[self.case],'outputs':{'one':self.answer}}))
            run=subprocess.run([sys.executable,str(root/'scripts/evaluate_source_answers.py'),str(p)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertFalse(json.loads(run.stdout)['semantic_quality_verified'])
            p.write_text('{"cases":[],"cases":[]}')
            run=subprocess.run([sys.executable,str(root/'scripts/evaluate_source_answers.py'),str(p)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)

if __name__ == '__main__': unittest.main()
