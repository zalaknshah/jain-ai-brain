"""Keep the honest readiness diagnostic observable; not a doctrine pass gate."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('readiness',ROOT/'scripts/evaluate_reasoning_readiness.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReasoningReadinessTests(unittest.TestCase):
    def test_diagnostic_runs_real_local_engine_and_keeps_failure_outputs(self):
        report=module.run()
        self.assertEqual(report['observations']['case_count'],16)
        self.assertEqual(report['observations']['cases_with_reviewed_evidence'],0)
        self.assertIn('not scored',report['observations']['doctrinal_correctness'])
        self.assertEqual(len({x['id'] for x in report['cases']}),16)
        self.assertTrue(all(x['response'] and x['requested_capability'] for x in report['cases']))
        self.assertTrue(any(x['family']=='doctrine' for x in report['cases']))
        self.assertTrue(any(x['family']=='multilingual' for x in report['cases']))
        # Do not assert the current defect count forever: improvements are allowed.
        # The diagnostic must report actual outputs instead of claiming a pass.
        requested=[x for x in report['cases'] if x['expected_plan']]
        self.assertEqual(report['observations']['requested_template_present'],sum(x['expected_template_present'] for x in requested))
        sources=[x for x in report['cases'] if x['source_question_fixture']]
        self.assertEqual(len(sources),5)
        self.assertEqual(report['observations']['source_first_responses'],sum(x['source_first_response_present'] for x in sources))
        self.assertEqual(report['observations']['source_questions_with_practical_templates'],sum(x['practical_template_present'] for x in sources))


if __name__=='__main__':unittest.main()
