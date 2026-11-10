"""Keep actual citation-validator outcomes visible, including unsupported answers."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('semantic_support_diagnostic', ROOT/'scripts/evaluate_semantic_support.py')
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class SemanticSupportDiagnosticTests(unittest.TestCase):
    def test_fixtures_have_explicit_labels_rationales_and_only_exact_original_quotes(self):
        fixtures = json.loads((ROOT/'evals/semantic_support_cases.json').read_text())
        self.assertEqual(len(fixtures['cases']), 14)
        self.assertEqual(len({case['id'] for case in fixtures['cases']}), 14)
        for case in fixtures['cases']:
            self.assertIn(case['semantic_label'], {'supported', 'contradicted', 'not-established'})
            self.assertTrue(case['rationale'])
            records = {row['entry_id']: row for row in case['records']}
            for record in records.values():
                self.assertIs(record['verified'], True)
                self.assertIn('Original', record['source'])
                self.assertEqual(record['language'], 'en')
            for citation in case['content']['citations']:
                self.assertIn(citation['quote'], records[citation['entry_id']]['principle'])

    def test_results_use_real_validator_and_keep_full_actual_outputs(self):
        original = diagnostic.check_model_output
        with patch.object(diagnostic, 'check_model_output', wraps=original) as observed:
            report = diagnostic.run()
        self.assertEqual(observed.call_count, 14)
        self.assertFalse(report['semantic_labels_produced_by_system'])
        self.assertIn('not labels produced by the validator', report['label_origin'])
        for case in report['cases']:
            if case['mechanically_accepted']:
                self.assertEqual(case['actual_answer'], case['input_answer'])
                self.assertEqual(case['actual_citations'], case['input_citations'])
                self.assertIn('does not establish', case['actual_rendered_output'])
            else:
                self.assertTrue(case['actual_error'])

    def test_aggregation_describes_actual_results_not_an_assumed_semantic_pass(self):
        report = diagnostic.run(); rows = report['cases']; observations = report['observations']
        self.assertEqual(observations['case_count'], len(rows))
        self.assertEqual(observations['mechanically_accepted_total'], sum(row['mechanically_accepted'] for row in rows))
        self.assertEqual(observations['mechanically_accepted_without_source_support'], sum(
            row['mechanically_accepted'] and row['author_semantic_label'] != 'supported' for row in rows))
        self.assertNotIn('passed', report)
        self.assertNotIn('accuracy', observations)
        self.assertEqual(observations['author_label_counts'], {'contradicted': 6, 'not-established': 3, 'supported': 5})

    def test_future_rejections_are_reported_without_freezing_today_acceptance_gap(self):
        with patch.object(diagnostic, 'check_model_output', side_effect=ValueError('synthetic future rejection')):
            report = diagnostic.run()
        self.assertEqual(report['observations']['mechanically_accepted_total'], 0)
        self.assertEqual(report['observations']['mechanically_accepted_without_source_support'], 0)
        self.assertTrue(all(row['actual_error'] == 'synthetic future rejection' for row in report['cases']))

    def test_unknown_is_not_mislabeled_as_contradiction(self):
        cases = {row['id']: row for row in diagnostic.run()['cases']}
        for ident in ('all_from_some', 'condition_unmet', 'cross_source_link'):
            self.assertEqual(cases[ident]['author_semantic_label'], 'not-established')

    def test_cli_is_fixed_fixture_only_and_ignores_provider_and_corpus_configuration(self):
        environment = dict(os.environ, JACE_LLM_URL='http://127.0.0.1:1/never', JACE_CANONICAL_PATH='/missing/never.json')
        result = subprocess.run([sys.executable, str(ROOT/'scripts/evaluate_semantic_support.py')],
                                env=environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['observations']['case_count'], 14)


if __name__ == '__main__':
    unittest.main()
