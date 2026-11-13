"""Synthetic saved responses only; no models, literature or claimed expert review."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from jace.source_answer_eval import compare_source_answers, evaluate_source_answers


class PairedSourceAnswerTests(unittest.TestCase):
    def setUp(self):
        source = {'entry_id': 'fixture', 'title': 'Fixture', 'principle': 'Wait for confirmation.',
                  'guidance': 'Original synthetic guidance.', 'source': 'Synthetic fixture',
                  'work': 'Fixture', 'language': 'en', 'location': 'line 1', 'license': 'MIT', 'verified': True}
        self.cases = [{'id': 'one', 'question': 'What next?', 'require_citation': True, 'evidence': [source]},
                      {'id': 'two', 'question': 'And now?', 'require_citation': True, 'evidence': [source]}]
        self.answer = json.dumps({'answer': 'Wait.', 'citations': [{'entry_id': 'fixture', 'quote': 'Wait for confirmation.'}]})
        self.baseline = {'outputs': {'one': self.answer, 'two': self.answer}}

    def compare(self, candidate):
        return compare_source_answers(self.cases, self.baseline, candidate)

    def review(self, outputs, verdict='supported'):
        report = evaluate_source_answers(self.cases, outputs)
        return {r['id']: {'review_binding_sha256': r['review_binding_sha256'], 'verdict': verdict,
                         'reviewer': 'synthetic-test-only', 'rationale': 'Original test annotation.'}
                for r in report['cases'] if r['mechanical'] != 'missing'}

    def test_identical_outputs_are_paired_without_semantic_promotion(self):
        report = self.compare(copy.deepcopy(self.baseline))
        self.assertEqual(report['coverage'], {'paired_outputs': 2, 'paired_reviews': 0})
        self.assertTrue(all(v == 0 for v in report['loss_counts'].values()))
        for key in ('semantic_quality_verified', 'runtime_admitted', 'winner_selected'):
            self.assertIs(report[key], False)

    def test_missing_candidate_remains_denominator_and_loss(self):
        report = self.compare({'outputs': {}})
        self.assertEqual(report['case_count'], 2)
        self.assertEqual(report['coverage']['paired_outputs'], 0)
        self.assertEqual(report['loss_counts']['output_lost'], 2)
        self.assertEqual(report['loss_counts']['mechanical_acceptance_lost'], 2)
        self.assertEqual(report['loss_counts']['citation_requirement_lost'], 2)

    def test_gain_does_not_cancel_other_case_regression(self):
        self.baseline['outputs']['two'] = 'invalid'
        report = self.compare({'outputs': {'one': 'invalid', 'two': self.answer}})
        self.assertEqual(report['baseline']['mechanically_accepted'], report['candidate']['mechanically_accepted'])
        self.assertEqual(report['loss_counts']['mechanical_acceptance_lost'], 1)
        self.assertTrue(report['pairs'][0]['mechanical_acceptance_lost'])

    def test_citation_loss_separate_from_valid_json(self):
        report = self.compare({'outputs': {'one': json.dumps({'answer': 'Wait.', 'citations': []})}})
        self.assertEqual(report['candidate']['mechanically_accepted'], 1)
        self.assertEqual(report['loss_counts']['citation_requirement_lost'], 2)

    def test_unreviewed_candidate_not_silently_supported(self):
        self.baseline['reviews'] = self.review(self.baseline['outputs'])
        report = self.compare({'outputs': dict(self.baseline['outputs'])})
        self.assertEqual(report['human_annotation_transitions'], {'supported_to_unreviewed': 2})
        self.assertEqual(report['coverage']['paired_reviews'], 0)
        self.assertEqual(report['loss_counts']['supported_annotation_lost'], 2)

    def test_annotation_changes_stay_explicit_and_unverified(self):
        self.baseline['reviews'] = self.review(self.baseline['outputs'])
        candidate = {'outputs': dict(self.baseline['outputs']), 'reviews': self.review(self.baseline['outputs'], 'unsupported')}
        report = self.compare(candidate)
        self.assertEqual(report['human_annotation_transitions'], {'supported_to_unsupported': 2})
        self.assertEqual(report['coverage']['paired_reviews'], 2)
        self.assertFalse(report['semantic_quality_verified'])

    def test_stale_baseline_review_cannot_grade_changed_candidate(self):
        candidate = copy.deepcopy(self.baseline)
        candidate['reviews'] = self.review(candidate['outputs'])
        candidate['outputs']['one'] += ' '
        with self.assertRaises(ValueError): self.compare(candidate)

    def test_schema_rejects_separate_candidate_case_set_and_unknown_outputs(self):
        for candidate in ({'outputs': {}, 'cases': self.cases}, {'outputs': {'other': self.answer}},
                          {'outputs': {'one': None}}, [], {'reviews': {}}):
            with self.assertRaises(ValueError): self.compare(candidate)

    def test_declared_set_binding_order_independent_but_content_sensitive(self):
        original = self.compare(self.baseline)['declared_case_set_sha256']
        self.cases.reverse()
        self.assertEqual(original, self.compare(self.baseline)['declared_case_set_sha256'])
        self.cases[0]['question'] = 'Changed question?'
        self.assertNotEqual(original, self.compare(self.baseline)['declared_case_set_sha256'])

    def test_source_change_changes_declared_set_binding(self):
        original = self.compare(self.baseline)['declared_case_set_sha256']
        self.cases[0]['evidence'][0]['location'] = 'line 2'
        self.assertNotEqual(original, self.compare(self.baseline)['declared_case_set_sha256'])

    def test_summary_does_not_expose_private_text(self):
        self.baseline['reviews'] = self.review(self.baseline['outputs'])
        report = json.dumps(self.compare(self.baseline))
        for value in ('What next?', 'Wait for confirmation.', 'synthetic-test-only', 'Original test annotation.'):
            self.assertNotIn(value, report)

    def test_cli_comparison_is_explicit_and_does_not_write_files(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/evaluate_source_answers.py'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.json'
            p.write_text(json.dumps({'cases': self.cases, 'baseline': self.baseline, 'candidate': {'outputs': {}}}))
            result = subprocess.run([sys.executable, str(script), '--compare', str(p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['loss_counts']['output_lost'], 2)
            self.assertEqual(list(Path(d).iterdir()), [p])
            result = subprocess.run([sys.executable, str(script), str(p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__': unittest.main()
