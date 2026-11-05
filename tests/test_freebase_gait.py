import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from jace.freebase_gait import run_gait_probe, validate_gait_runtime
from jace.freebase_gait_metrics import summarize_two_step_probe

ROOT = Path(__file__).resolve().parents[1]
try:
    validate_gait_runtime()
    QUALIFIED_GAIT_RUNTIME = True
except RuntimeError:
    QUALIFIED_GAIT_RUNTIME = False
REAL = (os.name == 'posix' and sys.platform == 'linux'
        and QUALIFIED_GAIT_RUNTIME and importlib.util.find_spec('mujoco'))


class GaitContractTests(unittest.TestCase):
    def setUp(self):
        # These launcher-contract checks do not execute numerical work. Dedicated
        # runtime tests below exercise version checking without this stub.
        preflight = patch('jace.freebase_gait.validate_gait_runtime')
        preflight.start()
        self.addCleanup(preflight.stop)

    def test_no_worker_for_missing_confirmation_or_invalid_inputs(self):
        with patch('jace.freebase.subprocess.run') as worker:
            for options in ({}, {'confirm_simulation': 1}, {'confirm_simulation': 'yes'},
                            {'confirm_simulation': True, 'steps': 2001},
                            {'confirm_simulation': True, 'steps': False},
                            {'confirm_simulation': True, 'scenario': 'custom-model.xml'},
                            {'confirm_simulation': True, 'include_trace': 1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    run_gait_probe(**options)
            worker.assert_not_called()

    def test_worker_is_capped_isolated_and_does_not_retry(self):
        response = subprocess.CompletedProcess([], 0, '{"schema":"jace.freebase.gait_probe.v1"}', '')
        with patch.dict(os.environ, {'SYNTHETIC_TEST_SECRET': 'not-a-credential'}):
            with patch('jace.freebase.subprocess.run', return_value=response) as worker:
                run_gait_probe(confirm_simulation=True)
        args, kwargs = worker.call_args
        self.assertIn('jace.freebase_gait_worker', args[0])
        self.assertIn('--confirmed-simulation', args[0])
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['env']['OPENBLAS_NUM_THREADS'], '1')
        self.assertNotIn('SYNTHETIC_TEST_SECRET', kwargs['env'])
        with patch('jace.freebase.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 30)) as worker:
            with self.assertRaises(RuntimeError):
                run_gait_probe(confirm_simulation=True)
            self.assertEqual(worker.call_count, 1)

    def test_balance_report_is_not_mistaken_for_gait(self):
        response = subprocess.CompletedProcess([], 0, '{"schema":"jace.freebase.balance.v1"}', '')
        with patch('jace.freebase.subprocess.run', return_value=response):
            with self.assertRaises(RuntimeError):
                run_gait_probe(confirm_simulation=True)

    def test_cli_without_confirmation_does_not_start_physics(self):
        result = subprocess.run([sys.executable, '-m', 'jace.cli', 'probe-gait'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('explicit simulation confirmation', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_empty_or_sliding_trace_cannot_be_a_two_step_sequence(self):
        feet = [[0., .1, .03], [0., -.1, .03]]
        for trace in ([], [{'t': i * .004, 'phase': 'recover', 'contacts': [6, 6],
                           'normal_forces_n': [160., 160.], 'foot_clearance_m': [0., 0.]}
                          for i in range(2000)]):
            report = summarize_two_step_probe(trace, [], feet, [[.04, .1, .03], [.08, -.1, .03]],
                                              [0., 0., .78], [.035, 0., .75], [0., 0.], 8.)
            self.assertFalse(report['two_step_sequence_observed'])
            self.assertFalse(report['both_feet_cleared_and_landed'])
            self.assertFalse(report['ordered_alternating_support_observed'])


@unittest.skipUnless(REAL, 'Python 3.12+, Linux and exact gait dependencies required; numerical gait probe not run')
class RealGaitProbeTests(unittest.TestCase):
    def test_actual_two_steps_are_measured_without_general_walking_claim(self):
        report = run_gait_probe(confirm_simulation=True, include_trace=True)
        self.assertEqual(report['steps'], 2000)
        self.assertEqual(report['terminal_reason'], 'step_budget_reached')
        self.assertTrue(report['two_step_probe_accepted'])
        self.assertTrue(report['ordered_alternating_support_observed'])
        self.assertTrue(report['both_feet_cleared_and_landed'])
        self.assertTrue(report['last_second_double_support_observed'])
        self.assertGreater(report['settled_tail_s'], 1.)
        self.assertGreater(report['net_pelvis_advance_m'], .03)
        self.assertLess(report['maximum_tilt_rad'], .03)
        self.assertGreater(report['foot_body_displacements_m'][0][0], .035)
        self.assertGreater(report['foot_body_displacements_m'][1][0], .075)
        self.assertTrue(all(value > .03 for value in report['maximum_foot_capsule_clearance_m']))
        self.assertEqual([event['to'] for event in report['phase_transitions']],
                         ['shift_right', 'swing_left', 'shift_left', 'swing_right', 'recover'])
        self.assertEqual(report['final_gait_observation']['sample_kind'], 'final_post_step')
        self.assertAlmostEqual(report['final_gait_observation']['t'], 8.)
        self.assertEqual(len(report['gait_trace']), 2001)
        self.assertEqual(report['gait_trace'][-1], report['final_gait_observation'])
        self.assertGreater(report['out_of_planned_swing_airborne_observations']['left'], 0)
        self.assertGreater(report['out_of_planned_swing_airborne_observations']['right'], 0)
        self.assertTrue(report['locomotion_controller'])
        self.assertEqual(report['controller_status'], 'experimental_two_step_only')
        for key in ('walking_verified', 'balance_qualified', 'standing_verified', 'hardware_enabled',
                    'external_support_enabled', 'root_state_written_during_episode', 'pretrained_policy_loaded'):
            self.assertFalse(report[key], key)
        self.assertEqual(report['resource_limits']['address_space_bytes'], 1024**3)
        self.assertEqual(report['resource_limits']['cpu_seconds'], 15)
        json.dumps(report, allow_nan=False)

    def test_strong_push_is_failure_even_when_process_returns_a_report(self):
        report = run_gait_probe('strong_forward_first_swing', confirm_simulation=True)
        self.assertEqual(report['terminal_reason'], 'posture_guard_triggered')
        self.assertFalse(report['two_step_probe_accepted'])
        self.assertFalse(report['finite_horizon_posture_accepted'])
        self.assertLess(report['steps'], 2000)
        self.assertLess(report['minimum_pelvis_height_m'], .55)

    def test_dropouts_and_bad_initial_state_stop_before_another_step(self):
        for scenario, count, reason in (('initial_tilt', 0, 'posture_guard_triggered'),
                                       ('sensor_dropout', 100, 'sensor_guard_triggered')):
            with self.subTest(scenario=scenario):
                report = run_gait_probe(scenario, confirm_simulation=True)
                self.assertEqual(report['steps'], count)
                self.assertEqual(report['terminal_reason'], reason)
                self.assertFalse(report['two_step_probe_accepted'])

    def test_short_horizon_and_repeatability(self):
        report = run_gait_probe(steps=10, confirm_simulation=True)
        self.assertTrue(report['no_guard_triggered_within_horizon'])
        self.assertFalse(report['two_step_probe_accepted'])
        first = run_gait_probe('small_lateral_first_swing', confirm_simulation=True)
        second = run_gait_probe('small_lateral_first_swing', confirm_simulation=True)
        first.pop('peak_rss_kib'); second.pop('peak_rss_kib')
        self.assertEqual(first, second)

    def test_controller_infeasibility_stops_before_another_physics_step(self):
        code = """
import json, sys
if sys.argv[1] != '--confirmed-simulation':
    raise ValueError('simulation confirmation required')
from jace.freebase_worker import _apply_resource_limits, _run
_apply_resource_limits()
from jace.freebase_gait import ControllerFeasibilityError
from jace.freebase_gait_controller import ContactGaitPrototype
original = ContactGaitPrototype.command
def inject(self, data):
    if data.time >= .004:
        raise ControllerFeasibilityError('synthetic independent solver failure')
    return original(self, data)
ContactGaitPrototype.command = inject
print(json.dumps(_run('neutral_posture', 2000, False, confirm_simulation=True,
                     controller='contact_gait'), allow_nan=False))
"""
        env = {'PATH': os.defpath, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHONNOUSERSITE': '1',
               'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
        result = subprocess.run([sys.executable, '-c', code, '--confirmed-simulation'], env=env,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['steps'], 1)
        self.assertAlmostEqual(report['elapsed_simulation_s'], .004)
        self.assertEqual(report['terminal_reason'], 'controller_feasibility_guard_triggered')
        self.assertFalse(report['two_step_probe_accepted'])
        self.assertFalse(report['no_guard_triggered_within_horizon'])
        self.assertIn('synthetic independent solver failure', report['controller_failure_detail'])
