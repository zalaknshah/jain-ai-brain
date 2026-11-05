"""Source/archived-counter regressions only: no physics worker is run here."""
import copy
import json
import math
import subprocess
import unittest
from unittest.mock import patch
from jace.freebase_sustained_resources import apply_observed_resource_verdict
from jace.freebase_sustained import run_sustained_probe


def fixture():
    return {'schema': 'jace.freebase.sustained_probe.v1', 'steps': 5000,
            'terminal_reason': 'step_budget_reached',
            'finite_horizon_posture_accepted': True, 'six_step_sequence_observed': True,
            'last_second_double_support_observed': True, 'sustained_probe_accepted': True,
            'worker_cpu_seconds_used': 10., 'worker_elapsed_wall_seconds': 12.,
            'outer_elapsed_wall_seconds': 12.2,
            'net_pelvis_advance_m': .1947829426938574,
            'resource_limits': {'address_space_bytes': 1024**3, 'cpu_seconds': 15,
                                'outer_wall_seconds': 30}}


class ObservedResourceVerdictTests(unittest.TestCase):
    def test_archived_installed_overage_preserves_physical_success_but_rejects_acceptance(self):
        report = fixture()
        report.update(worker_cpu_seconds_used=15.80148,
                      worker_elapsed_wall_seconds=24.875193871033844,
                      outer_elapsed_wall_seconds=25.074059182952624)
        before = copy.deepcopy(report)
        apply_observed_resource_verdict(report, include_outer_wall=True)
        self.assertTrue(report['physical_six_step_criteria_met'])
        self.assertFalse(report['observed_resource_budget_satisfied'])
        self.assertFalse(report['sustained_probe_accepted'])
        self.assertEqual(report['resource_budget_violations'], ['worker_cpu_seconds_used_exceeded'])
        for key in before:
            if key != 'sustained_probe_accepted':
                self.assertEqual(report[key], before[key], key)
        self.assertFalse(report['resource_accounting_scope']['full_worker_lifetime_cpu_measured'])
        self.assertFalse(report['resource_accounting_scope']['resource_reliability_qualified'])

    def test_boundaries_are_exact_observed_budgets_not_os_tolerances(self):
        for key, budget in (('worker_cpu_seconds_used', 15.),
                            ('worker_elapsed_wall_seconds', 30.),
                            ('outer_elapsed_wall_seconds', 30.)):
            for value, accepted in ((budget, True), (math.nextafter(budget, math.inf), False)):
                with self.subTest(key=key, value=value):
                    report = fixture(); report[key] = value
                    apply_observed_resource_verdict(report, include_outer_wall=True)
                    self.assertEqual(report['sustained_probe_accepted'], accepted)

    def test_absent_invalid_and_nonfinite_usage_cannot_pass(self):
        for key in ('worker_cpu_seconds_used', 'worker_elapsed_wall_seconds',
                    'outer_elapsed_wall_seconds'):
            for value in (None, True, '1', -1., float('nan'), float('inf')):
                with self.subTest(key=key, value=value):
                    report = fixture(); report[key] = value
                    apply_observed_resource_verdict(report, include_outer_wall=True)
                    self.assertFalse(report['sustained_probe_accepted'])
                    self.assertIn(key + '_missing_or_invalid', report['resource_budget_violations'])
            report = fixture(); report.pop(key)
            apply_observed_resource_verdict(report, include_outer_wall=True)
            self.assertFalse(report['sustained_probe_accepted'])

    def test_caps_must_still_be_exactly_the_original_configuration(self):
        for key in ('cpu_seconds', 'outer_wall_seconds', 'address_space_bytes'):
            for value in (None, True, 999999999999, 0):
                with self.subTest(key=key, value=value):
                    report = fixture(); report['resource_limits'][key] = value
                    apply_observed_resource_verdict(report, include_outer_wall=True)
                    self.assertFalse(report['sustained_probe_accepted'])

    def test_physical_failure_and_short_prefix_remain_failures(self):
        for key, value in (('steps', 4999), ('terminal_reason', 'unexpected_contact_detected'),
                           ('finite_horizon_posture_accepted', False),
                           ('six_step_sequence_observed', False),
                           ('last_second_double_support_observed', False)):
            report = fixture(); report[key] = value
            apply_observed_resource_verdict(report, include_outer_wall=True)
            self.assertFalse(report['physical_six_step_criteria_met'])
            self.assertFalse(report['sustained_probe_accepted'])
            self.assertTrue(report['observed_resource_budget_satisfied'])

    def test_worker_stage_is_explicit_and_launcher_reassesses_later_time(self):
        report = fixture(); report.pop('outer_elapsed_wall_seconds')
        apply_observed_resource_verdict(report, include_outer_wall=False)
        self.assertTrue(report['sustained_probe_accepted'])
        self.assertEqual(report['resource_verdict_stage'], 'worker_report')
        report['outer_elapsed_wall_seconds'] = 30.01
        apply_observed_resource_verdict(report, include_outer_wall=True)
        self.assertFalse(report['sustained_probe_accepted'])
        self.assertEqual(report['resource_verdict_stage'], 'launcher_return')

    def test_launcher_rejects_an_overbudget_worker_that_claims_acceptance(self):
        report = fixture(); report['worker_cpu_seconds_used'] = 15.80148
        response = subprocess.CompletedProcess([], 0, json.dumps(report), '')
        with patch('jace.freebase_sustained.validate_gait_runtime'), patch(
                'jace.freebase_sustained.subprocess.run', return_value=response) as worker:
            result = run_sustained_probe(confirm_simulation=True)
        self.assertEqual(worker.call_count, 1)
        self.assertTrue(result['physical_six_step_criteria_met'])
        self.assertFalse(result['sustained_probe_accepted'])
        self.assertIn('worker_cpu_seconds_used_exceeded', result['resource_budget_violations'])

    def test_launcher_gate_includes_its_own_outer_measurement(self):
        response = subprocess.CompletedProcess([], 0, json.dumps(fixture()), '')
        with patch('jace.freebase_sustained.validate_gait_runtime'), patch(
                'jace.freebase_sustained.subprocess.run', return_value=response), patch(
                'jace.freebase_sustained.time.monotonic', side_effect=[100., 130.01]):
            result = run_sustained_probe(confirm_simulation=True)
        self.assertFalse(result['sustained_probe_accepted'])
        self.assertIn('outer_elapsed_wall_seconds_exceeded', result['resource_budget_violations'])

    def test_lower_cpu_sample_does_not_claim_whole_lifetime_compliance(self):
        report = fixture()
        apply_observed_resource_verdict(report, include_outer_wall=True)
        self.assertTrue(report['sustained_probe_accepted'])
        self.assertFalse(report['resource_accounting_scope']['full_worker_lifetime_cpu_measured'])
        self.assertFalse(report['resource_accounting_scope']['resource_reliability_qualified'])

    def test_launcher_preserves_malformed_limit_evidence_without_accepting(self):
        for value in (None, [], 'not a mapping'):
            report = fixture(); report['resource_limits'] = value
            response = subprocess.CompletedProcess([], 0, json.dumps(report), '')
            with patch('jace.freebase_sustained.validate_gait_runtime'), patch(
                    'jace.freebase_sustained.subprocess.run', return_value=response):
                result = run_sustained_probe(confirm_simulation=True)
            self.assertEqual(result['resource_limits'], value)
            self.assertTrue(result['physical_six_step_criteria_met'])
            self.assertFalse(result['sustained_probe_accepted'])
            self.assertFalse(result['observed_resource_budget_satisfied'])
