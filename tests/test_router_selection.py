import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('selection', ROOT / 'scripts/calibrate_router_selection.py')
selection = importlib.util.module_from_spec(spec); spec.loader.exec_module(selection)


class RouterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.cached = [dict(id='positive', relevant=['yes'], top='yes', score=.6, margin=.2),
                       dict(id='negative', relevant=[], top='yes', score=.5, margin=.05),
                       dict(id='wrong', relevant=['no'], top='yes', score=.7, margin=.01)]
        self.model = {'synthetic': True}
        self.rule = {'schema_version': 1, 'policy': selection.POLICY,
                     'model_sha256': selection.digest(selection.encoded(self.model)),
                     'development_sha256': 'a' * 64,
                     'development_query_hashes': [selection.query_hash('one'), selection.query_hash('two')],
                     'threshold': .4, 'margin': .1, 'development': {},
                     'runtime_admitted': False, 'semantic_quality_verified': False}

    def test_margin_blocks_high_score_wrong_and_unrelated(self):
        r = selection.selected_results(self.cached, .4, .1)
        self.assertEqual((r['accepted'], r['correct_accepted'], r['incorrect_accepted']), (1, 1, 0))
        self.assertEqual(r['positive_abstentions'], 1)
        self.assertEqual(r['negative_rejected'], 1)

    def test_score_alone_can_accept_false_selections(self):
        r = selection.selected_results(self.cached, .4, 0)
        self.assertEqual(r['incorrect_accepted'], 2)

    def test_all_abstain_is_reported_not_hidden(self):
        r = selection.selected_results(self.cached, 1.000001, .3)
        self.assertEqual(r['accepted'], 0)
        self.assertEqual(r['positive_abstentions'], 2)
        self.assertEqual(r['correct_decisions'], 1)

    def test_calibration_uses_zero_error_then_coverage_and_strict_ties(self):
        development = [{'query': 'new one'}, {'query': 'new two'}]
        with patch.object(selection, 'cached_scores', return_value=self.cached):
            rule = selection.calibrate_selection({'corpus': []}, self.model, development, 'c' * 64)
        self.assertEqual((rule['threshold'], rule['margin']), (.6, .2))
        self.assertEqual(rule['development']['incorrect_accepted'], 0)
        self.assertEqual(rule['development']['correct_accepted'], 1)
        self.assertFalse(rule['runtime_admitted'])

    def test_no_useful_development_acceptance_selects_all_abstain(self):
        wrong = [dict(id='wrong', relevant=['no'], top='yes', score=.9, margin=.2)]
        with patch.object(selection, 'cached_scores', return_value=wrong):
            rule = selection.calibrate_selection({'corpus': []}, self.model, [{'query': 'new'}], 'c' * 64)
        self.assertEqual((rule['threshold'], rule['margin']), (1.000001, .3))
        self.assertEqual(rule['development']['positive_abstentions'], 1)

    def test_model_binding_and_grid_validation(self):
        self.assertEqual(selection.validate_selection(self.rule, self.model, [{'query': 'fresh'}]), (.4, .1))
        for key, value in [('model_sha256', 'b' * 64), ('threshold', .401), ('margin', .11),
                           ('runtime_admitted', True), ('semantic_quality_verified', True), ('schema_version', True)]:
            rule = dict(self.rule, **{key: value})
            with self.assertRaises(ValueError): selection.validate_selection(rule, self.model, [{'query': 'fresh'}])

    def test_normalized_development_overlap_rejected(self):
        with self.assertRaises(ValueError): selection.validate_selection(self.rule, self.model, [{'query': ' ONE  '}])

    def test_unknown_schema_rejected(self):
        rule = dict(self.rule, extra=True)
        with self.assertRaises(ValueError): selection.validate_selection(rule, self.model, [{'query': 'fresh'}])

    def test_selection_object_is_not_mutated(self):
        before = copy.deepcopy(self.rule)
        selection.validate_selection(self.rule, self.model, [{'query': 'fresh'}])
        self.assertEqual(before, self.rule)


if __name__ == '__main__': unittest.main()
