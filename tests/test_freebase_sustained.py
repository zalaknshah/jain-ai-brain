import importlib.util
import json
import os
from pathlib import Path
import subprocess
from jace.worker_accounting import AccountedWorker
import sys
import unittest
from unittest.mock import patch

from jace.freebase_sustained import run_sustained_probe, validate_gait_runtime
from jace.freebase_sustained_metrics import summarize_sustained_probe, EXPECTED_PHASES

ROOT = Path(__file__).resolve().parents[1]
try:
    validate_gait_runtime()
    QUALIFIED = True
except RuntimeError:
    QUALIFIED = False
REAL = (os.name == 'posix' and sys.platform == 'linux' and QUALIFIED
        and importlib.util.find_spec('mujoco'))


class SustainedContractTests(unittest.TestCase):
    def setUp(self):
        preflight = patch('jace.freebase_sustained.validate_gait_runtime')
        preflight.start()
        self.addCleanup(preflight.stop)

    def test_invalid_inputs_and_no_confirmation_never_spawn(self):
        with patch('jace.freebase_sustained.run_accounted_worker') as worker:
            for options in ({}, {'confirm_simulation': 1}, {'confirm_simulation': 'yes'},
                            {'confirm_simulation': True, 'steps': 5001},
                            {'confirm_simulation': True, 'steps': 0},
                            {'confirm_simulation': True, 'steps': False},
                            {'confirm_simulation': True, 'steps': 1.0},
                            {'confirm_simulation': True, 'scenario': 'custom.xml'},
                            {'confirm_simulation': True, 'include_trace': 1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    run_sustained_probe(**options)
            worker.assert_not_called()

    def test_capped_isolated_worker_no_retry(self):
        response = AccountedWorker(0, '{"schema":"jace.freebase.sustained_probe.v1"}', '', 10.25)
        with patch.dict(os.environ, {'SYNTHETIC_TEST_SECRET': 'not-a-credential'}):
            with patch('jace.freebase_sustained.run_accounted_worker', return_value=response) as worker:
                run_sustained_probe(confirm_simulation=True)
        args, kwargs = worker.call_args
        self.assertIn('jace.freebase_sustained_worker', args[0])
        self.assertIn('5000', args[0])
        self.assertIn('--confirmed-simulation', args[0])
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['env']['OPENBLAS_NUM_THREADS'], '1')
        self.assertNotIn('SYNTHETIC_TEST_SECRET', kwargs['env'])
        with patch('jace.freebase_sustained.run_accounted_worker', side_effect=subprocess.TimeoutExpired('worker', 30)) as worker:
            with self.assertRaises(RuntimeError):
                run_sustained_probe(confirm_simulation=True)
            self.assertEqual(worker.call_count, 1)

    def test_wrong_schema_or_failed_worker_is_not_success(self):
        for code, output in ((0, '{"schema":"jace.freebase.gait_probe.v1"}'), (0, 'not json'),
                             (-9, ''), (2, '')):
            response = AccountedWorker(code, output, 'synthetic worker error', 10.25)
            with patch('jace.freebase_sustained.run_accounted_worker', return_value=response):
                with self.assertRaises(RuntimeError):
                    run_sustained_probe(confirm_simulation=True)

    def test_old_lane_keeps_2000_step_limit(self):
        from jace.freebase_gait import run_gait_probe
        with patch('jace.freebase.subprocess.run') as worker:
            with self.assertRaises(ValueError):
                run_gait_probe(steps=5000, confirm_simulation=True)
            worker.assert_not_called()

    def test_script_requires_confirmation(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/probe_sustained_gait.py')],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('explicit simulation confirmation', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_empty_and_sliding_phase_commands_do_not_pass(self):
        feet = [[0., .1, .03], [0., -.1, .03]]
        events = [{'time': (i + 1) * .5, 'to': phase} for i, phase in enumerate(EXPECTED_PHASES)]
        for trace in ([], [{'t': i * .004, 'phase': 'recover', 'contacts': [6, 6],
                           'normal_forces_n': [160., 160.], 'foot_clearance_m': [0., 0.],
                           'feet': [[.2, .1, .03], [.24, -.1, .03]]} for i in range(5001)]):
            report = summarize_sustained_probe(trace, events, feet, [[.2, .1, .03], [.24, -.1, .03]],
                                              [0., 0., .78], [.19, 0., .75], [0., 0.], 20.)
            self.assertFalse(report['six_step_sequence_observed'])
            self.assertFalse(report['all_six_steps_measured'])

    def test_chatter_duration_excludes_durationless_final_snapshot(self):
        feet = [[0., .1, .03], [0., -.1, .03]]
        trace = [{'t': i * .004, 'phase': 'recover', 'contacts': [0, 6],
                  'normal_forces_n': [0., 320.], 'foot_clearance_m': [.001, 0.], 'feet': feet}
                 for i in range(3)]
        report = summarize_sustained_probe(trace, [], feet, feet, [0., 0., .78],
                                          [0., 0., .78], [.001, 0.], .008)
        self.assertEqual(report['contact_chatter']['left']['airborne_samples'], 2)
        self.assertAlmostEqual(report['contact_chatter']['left']['sampled_airborne_duration_s'], .008)
        self.assertEqual(report['contact_chatter']['left']['airborne_fraction_of_eligible_time'], 1.)


@unittest.skipUnless(REAL, 'Python 3.12+, Linux and exact gait stack required; no physics run')
class RealSustainedTests(unittest.TestCase):
    def test_six_continuous_steps_and_each_actual_step(self):
        report = run_sustained_probe(confirm_simulation=True, include_trace=True)
        self.assertEqual(report['steps'], 5000)
        self.assertAlmostEqual(report['elapsed_simulation_s'], 20.)
        self.assertEqual(report['terminal_reason'], 'step_budget_reached')
        self.assertTrue(report['sustained_probe_accepted'])
        self.assertEqual(len(report['gait_trace']), 5001)
        self.assertEqual([step['swing_foot'] for step in report['measured_steps']], ['left', 'right'] * 3)
        self.assertTrue(all(step['measured_step_accepted'] for step in report['measured_steps']))
        self.assertTrue(all(step['loaded_single_support_s'] > .5 for step in report['measured_steps']))
        self.assertGreater(report['net_pelvis_advance_m'], .19)
        self.assertGreater(report['settled_tail_s'], 4.)
        for key in ('walking_verified', 'balance_qualified', 'standing_verified', 'hardware_enabled',
                    'external_support_enabled', 'root_state_written_during_episode', 'pretrained_policy_loaded'):
            self.assertFalse(report[key], key)
        self.assertEqual(report['resource_limits']['address_space_bytes'], 1024**3)
        self.assertEqual(report['resource_limits']['cpu_seconds'], 15)
        self.assertEqual(report['resource_limits']['outer_wall_seconds'], 30)
        # Explicit nominal performance-headroom checks, not a claim that OS cap
        # granularity or outer JSON decoding always fits these exact counters.
        self.assertLess(report['worker_cpu_seconds_used'], 15)
        self.assertLess(report['outer_elapsed_wall_seconds'], 30)
        for side in ('left', 'right'):
            self.assertGreater(report['contact_chatter'][side]['airborne_samples'], 0)
            self.assertLess(report['contact_chatter'][side]['airborne_fraction_of_eligible_time'], .012)
        # Metrics must fail if any one real swing is replaced by contact-only sliding.
        damaged = [dict(row) for row in report['gait_trace']]
        third = report['measured_steps'][2]
        for row in damaged:
            if third['start_s'] <= row['t'] <= third['end_s']:
                row['contacts'] = [6, 6]
        false = summarize_sustained_probe(damaged, report['phase_transitions'],
            report['initial_foot_body_positions_m'], report['final_foot_body_positions_m'],
            report['initial_root_position_m'], report['final_root_position_m'],
            report['final_foot_capsule_clearance_m'], report['elapsed_simulation_s'])
        self.assertFalse(false['measured_steps'][2]['measured_step_accepted'])
        self.assertFalse(false['six_step_sequence_observed'])

    def test_guard_failures_and_short_horizon(self):
        for scenario, count, reason in (('initial_tilt', 0, 'posture_guard_triggered'),
                ('sensor_dropout', 100, 'sensor_guard_triggered'),
                ('strong_forward_third_swing', 1882, 'controller_feasibility_guard_triggered')):
            with self.subTest(scenario=scenario):
                report = run_sustained_probe(scenario, confirm_simulation=True)
                self.assertEqual(report['steps'], count)
                self.assertEqual(report['terminal_reason'], reason)
                self.assertFalse(report['sustained_probe_accepted'])
        report = run_sustained_probe(steps=10, confirm_simulation=True)
        self.assertFalse(report['sustained_probe_accepted'])
        self.assertEqual(report['steps'], 10)

    def test_deterministic_physical_replay(self):
        first = run_sustained_probe(confirm_simulation=True)
        second = run_sustained_probe(confirm_simulation=True)
        for report in (first, second):
            for key in ('peak_rss_kib', 'worker_cpu_seconds_used', 'worker_elapsed_wall_seconds',
                        'outer_elapsed_wall_seconds'):
                report.pop(key)
        self.assertEqual(first, second)
