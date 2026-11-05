import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from jace.freebase_balance import SCENARIOS, run_freebase_balance

ROOT = Path(__file__).resolve().parents[1]
REAL = os.name == 'posix' and sys.platform == 'linux' and importlib.util.find_spec('mujoco')


class BalanceContractTests(unittest.TestCase):
    def test_no_worker_without_valid_confirmation_and_bounded_options(self):
        with patch('jace.freebase.subprocess.run') as worker:
            for options in ({}, {'confirm_simulation': 'yes'}, {'confirm_simulation': 1},
                    {'confirm_simulation': True, 'steps': True}, {'confirm_simulation': True, 'steps': 0},
                    {'confirm_simulation': True, 'steps': 2001}, {'confirm_simulation': True, 'steps': 1.5},
                    {'confirm_simulation': True, 'include_trace': 1},
                    {'confirm_simulation': True, 'scenario': 'custom.xml'}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    run_freebase_balance(**options)
            worker.assert_not_called()

    def test_internal_runner_checks_confirmation_mode_and_budget(self):
        from jace.freebase_worker import _run
        for options in ({}, {'confirm_simulation': True, 'controller': 'custom'},
                        {'confirm_simulation': True, 'controller': 'posture_feedback', 'steps': 2001},
                        {'confirm_simulation': True, 'controller': 'posture_feedback', 'scenario': 'custom.xml'}):
            args = {'scenario': 'neutral_posture', 'steps': 10, 'include_trace': False, **options}
            with self.subTest(options=options), self.assertRaises(ValueError):
                _run(**args)

    def test_isolated_worker_caps_and_environment(self):
        response = subprocess.CompletedProcess([], 0, '{"schema":"jace.freebase.balance.v1"}', '')
        with patch.dict(os.environ, {'SECRET_SYNTHETIC_TEST': 'not-a-credential'}):
            with patch('jace.freebase.subprocess.run', return_value=response) as worker:
                run_freebase_balance(confirm_simulation=True)
        args, kwargs = worker.call_args
        self.assertIn('jace.freebase_balance_worker', args[0])
        self.assertIn('--confirmed-simulation', args[0])
        self.assertEqual(kwargs['timeout'], 30)
        self.assertNotIn('SECRET_SYNTHETIC_TEST', kwargs['env'])
        self.assertEqual(kwargs['env']['OMP_NUM_THREADS'], '1')
        self.assertEqual(kwargs['env']['OPENBLAS_NUM_THREADS'], '1')
        self.assertNotIn('shell', kwargs)

    def test_diagnostic_schema_or_failed_worker_is_not_balance_success(self):
        for result in (subprocess.CompletedProcess([], 0, '{"schema":"jace.freebase.diagnostic.v1"}', ''),
                       subprocess.CompletedProcess([], 137, '', 'killed')):
            with patch('jace.freebase.subprocess.run', return_value=result) as worker:
                with self.assertRaises(RuntimeError):
                    run_freebase_balance(confirm_simulation=True)
                self.assertEqual(worker.call_count, 1)

    def test_numerical_reset_cannot_be_accepted_as_finite_state(self):
        from jace.freebase_worker import NUMERICAL_WARNINGS, _numerical_guard_reason
        clear = {name: 0 for name in NUMERICAL_WARNINGS}
        self.assertIsNone(_numerical_guard_reason(clear, .004, .004))
        for name in NUMERICAL_WARNINGS:
            with self.subTest(warning=name):
                self.assertEqual(_numerical_guard_reason({**clear, name: 1}, .004, .004),
                                 'numerical_warning_guard_triggered')
        for bad_time in (0., float('nan'), float('inf')):
            with self.subTest(time=bad_time):
                self.assertEqual(_numerical_guard_reason(clear, bad_time, .004),
                                 'simulation_time_guard_triggered')

    def test_heldout_evaluator_requires_explicit_simulation_confirmation(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate_balance_heldout.py')],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--confirm-simulation is required', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_cli_without_confirmation_runs_no_physics(self):
        result = subprocess.run([sys.executable, '-m', 'jace.cli', 'simulate-balance'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('explicit simulation confirmation', result.stderr)
        self.assertEqual(result.stdout, '')


@unittest.skipUnless(REAL, 'Linux and optional MuJoCo required; numerical balance experiment not run')
class RealBalanceTests(unittest.TestCase):
    def test_neutral_finite_horizon_is_not_full_balance_or_walking(self):
        report = run_freebase_balance(confirm_simulation=True, include_trace=True)
        self.assertEqual(report['steps'], 2000)
        self.assertAlmostEqual(report['elapsed_simulation_s'], 8)
        self.assertEqual(report['terminal_reason'], 'step_budget_reached')
        self.assertTrue(report['finite_horizon_posture_accepted'])
        self.assertTrue(report['free_base'])
        for key in ('standing_verified', 'balance_qualified', 'walking_verified', 'locomotion_controller',
                    'pretrained_policy_loaded', 'hardware_enabled', 'external_support_enabled',
                    'root_state_written_during_episode'):
            self.assertFalse(report[key], key)
        self.assertTrue(report['controller_uses_exact_simulator_state'])
        self.assertLess(report['maximum_tilt_rad'], .025)
        self.assertGreater(report['minimum_pelvis_height_m'], .78)
        self.assertGreater(report['settled_tail_s'], 1)
        self.assertEqual(len(report['trace']), 2000)
        self.assertEqual(report['resource_limits']['cpu_seconds'], 15)
        self.assertEqual(report['resource_limits']['address_space_bytes'], 1024**3)
        self.assertEqual(report['nonfoot_floor_contact_observations'], 0)
        self.assertEqual(report['self_contact_observations'], 0)
        json.dumps(report, allow_nan=False)

    def test_modest_development_pushes_recover_within_measured_bounds(self):
        for scenario in ('backward_push', 'diagonal_push', 'reverse_lateral_push'):
            with self.subTest(scenario=scenario):
                report = run_freebase_balance(scenario, confirm_simulation=True)
                self.assertTrue(report['finite_horizon_posture_accepted'])
                self.assertLess(report['maximum_tilt_rad'], .1)
                self.assertGreater(report['minimum_pelvis_height_m'], .75)
                self.assertGreater(report['settled_tail_s'], 1)
                self.assertLess(abs(report['final_root_position_m'][0]), .1)
                self.assertLess(abs(report['final_root_position_m'][1]), .1)
                self.assertLess(report['maximum_joint_rate_rad_s'], 2)

    def test_original_strong_pushes_remain_explicit_failures(self):
        for scenario, reason in (('forward_push', 'posture_guard_triggered'),
                                 ('lateral_push', 'unexpected_contact_detected')):
            with self.subTest(scenario=scenario):
                report = run_freebase_balance(scenario, confirm_simulation=True)
                self.assertFalse(report['finite_horizon_posture_accepted'])
                self.assertFalse(report['no_guard_triggered_within_horizon'])
                self.assertEqual(report['terminal_reason'], reason)
                self.assertLess(report['steps'], 2000)

    def test_dropout_and_initial_bad_posture_stop_without_extra_step(self):
        for scenario, steps, reason in (('sensor_dropout', 100, 'sensor_guard_triggered'),
                                       ('initial_tilt', 0, 'posture_guard_triggered')):
            with self.subTest(scenario=scenario):
                report = run_freebase_balance(scenario, confirm_simulation=True)
                self.assertEqual(report['steps'], steps)
                self.assertEqual(report['terminal_reason'], reason)
                self.assertFalse(report['finite_horizon_posture_accepted'])

    def test_short_horizon_is_not_accepted_even_if_no_guard_triggers(self):
        report = run_freebase_balance(steps=10, confirm_simulation=True)
        self.assertTrue(report['no_guard_triggered_within_horizon'])
        self.assertFalse(report['finite_horizon_posture_accepted'])
        self.assertLessEqual(report['settled_tail_s'], .04)

    def test_numerical_reproducibility(self):
        first = run_freebase_balance('diagonal_push', confirm_simulation=True)
        second = run_freebase_balance('diagonal_push', confirm_simulation=True)
        first.pop('peak_rss_kib'); second.pop('peak_rss_kib')
        self.assertEqual(first, second)

    def test_controller_only_returns_finite_source_bounded_targets(self):
        import mujoco
        import numpy as np
        from jace.freebase_balance_controller import PostureFeedback
        model = mujoco.MjModel.from_xml_path(str(ROOT / 'src/jace/data/unitree_g1_scene.xml'))
        data = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, data, 0)
        mujoco.mj_forward(model, data)
        controller = PostureFeedback(model, data)
        before_qpos, before_qvel = data.qpos.copy(), data.qvel.copy()
        before_ctrl, before_support = data.ctrl.copy(), data.xfrc_applied.copy()
        command = controller.command(data)
        for before, after in ((before_qpos, data.qpos), (before_qvel, data.qvel),
                              (before_ctrl, data.ctrl), (before_support, data.xfrc_applied)):
            np.testing.assert_array_equal(before, after)
        self.assertTrue(np.all(np.isfinite(command)))
        self.assertTrue(np.all(command >= model.actuator_ctrlrange[:, 0]))
        self.assertTrue(np.all(command <= model.actuator_ctrlrange[:, 1]))
        data.qvel[6] = float('nan')
        with self.assertRaisesRegex(RuntimeError, 'nonfinite'):
            controller.command(data)

    def test_warning_or_clock_reset_after_genuine_step_fails_closed(self):
        code = """
import sys, json
if sys.argv[2] != '--confirmed-simulation':
    raise ValueError('simulation confirmation required')
from jace.freebase_worker import _apply_resource_limits, _run
_apply_resource_limits()
import mujoco
original = mujoco.mj_step
fault = sys.argv[1]
def inject(model, data):
    original(model, data)
    if fault == 'reset_time':
        data.time = 0.0
    else:
        data.warning[getattr(mujoco.mjtWarning, fault)].number += 1
mujoco.mj_step = inject
print(json.dumps(_run('neutral_posture', 2000, False, confirm_simulation=True,
                     controller='posture_feedback'), allow_nan=False))
"""
        env = {'PATH': os.defpath, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHONNOUSERSITE': '1',
               'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
        for fault in ('mjWARN_BADQPOS', 'mjWARN_BADQVEL', 'mjWARN_BADQACC', 'mjWARN_BADCTRL', 'reset_time'):
            with self.subTest(fault=fault):
                result = subprocess.run([sys.executable, '-c', code, fault, '--confirmed-simulation'],
                                        capture_output=True, text=True, env=env, timeout=30, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                expected = ('simulation_time_guard_triggered' if fault == 'reset_time'
                            else 'numerical_warning_guard_triggered')
                self.assertEqual(report['terminal_reason'], expected)
                self.assertEqual(report['steps'], 1)
                self.assertFalse(report['finite_horizon_posture_accepted'])
                self.assertFalse(report['no_guard_triggered_within_horizon'])

    def test_balanced_cli_is_explicit_and_reports_scope(self):
        result = subprocess.run([sys.executable, '-m', 'jace.cli', 'simulate-balance', '--steps', '10',
                                 '--confirm-simulation'], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['schema'], 'jace.freebase.balance.v1')
        self.assertFalse(report['finite_horizon_posture_accepted'])
