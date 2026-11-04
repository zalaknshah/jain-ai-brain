import importlib.util
import json
import math
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.articulated import run_articulation_scenario
from jace.reaching import plan_hand_target, run_hand_target

ROOT = Path(__file__).resolve().parents[1]
TARGET = (.3793621955923912, .22, 1.07070369520417)


def endpoint(shoulder, elbow):
    return (.28 * math.sin(shoulder) + .25 * math.sin(shoulder + elbow), .22,
            1.4 - .28 * math.cos(shoulder) - .25 * math.cos(shoulder + elbow))


class ReachContractTests(unittest.TestCase):
    def test_invalid_target_rejected_without_backend_or_dynamics(self):
        targets = [None, '0 .22 1', (1, 2), (True, .22, 1), (float('nan'), .22, 1),
                   (0, .22, float('inf')), (1e308, .22, 1), (0, .3, 1), (2, .22, 1),
                   (0, .22, 1.4), (0, .22, 1.1), (0, .22, 1.9), (10**1000, .22, 1)]
        with patch('jace.reaching.run_articulation_scenario') as simulation:
            for target in targets:
                with self.subTest(target=target), self.assertRaises(ValueError):
                    run_hand_target(target, confirm_simulation=True)
            simulation.assert_not_called()

    def test_joint_target_contract_rejects_invalid_values(self):
        for target in [(True, .3), (float('nan'), .4), (.7, .2), (.2, -.1), (.1,), 'a', (10**1000, .2)]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                run_articulation_scenario(left_arm_target_rad=target)


@unittest.skipUnless(importlib.util.find_spec('mujoco'), 'Optional MuJoCo dependency missing; real reaching test not run')
class RealReachTests(unittest.TestCase):
    def test_inverse_solution_matches_actual_forward_kinematics_including_boundaries(self):
        for shoulder in (-.1, -.05, 0, .15, .35, .55, .65):
            for elbow in (0, .2, .45, .65, .9):
                with self.subTest(shoulder=shoulder, elbow=elbow):
                    plan = plan_hand_target(endpoint(shoulder, elbow))
                    self.assertAlmostEqual(plan.shoulder_rad, shoulder, places=6)
                    self.assertAlmostEqual(plan.elbow_rad, elbow, places=6)
                    self.assertLess(plan.kinematic_residual_m, 1e-9)
                    self.assertFalse(plan.hardware_enabled)

    def test_planning_never_steps_dynamics(self):
        with patch('mujoco.mj_step', side_effect=AssertionError('planning actuated')):
            plan = plan_hand_target(TARGET)
        self.assertAlmostEqual(plan.shoulder_rad, .55)
        self.assertAlmostEqual(plan.elbow_rad, .65)

    def test_planner_rejects_drifted_asset_geometry_and_limits(self):
        from jace import reaching
        scene = (Path(reaching.__file__).with_name('data') / 'articulated_scene.xml').read_text()
        variants = [scene.replace('name="left_forearm" pos="0 0 -0.28"', 'name="left_forearm" pos="0 0 -0.30"'),
                    scene.replace('range="-0.1 0.65"', 'range="-0.1 0.50"')]
        for changed in variants:
            with self.subTest(changed=changed[-20:]), patch('jace.reaching.Path.read_text', return_value=changed):
                with self.assertRaises(RuntimeError):
                    plan_hand_target(TARGET)

    def test_nonfinite_forward_kinematics_is_rejected(self):
        def invalidate(model, data):
            data.geom_xpos[:] = float('nan')
        with patch('mujoco.mj_forward', side_effect=invalidate):
            with self.assertRaisesRegex(RuntimeError, 'forward kinematics'):
                plan_hand_target(TARGET)

    def test_reachable_targets_use_actual_dynamics_and_report_tracking_error(self):
        for shoulder, elbow in ((.15, .2), (.35, .45), (.55, .65), (.6, .85)):
            with self.subTest(shoulder=shoulder, elbow=elbow):
                report = run_hand_target(endpoint(shoulder, elbow), confirm_simulation=True)
                self.assertTrue(report.target_reached)
                self.assertTrue(report.within_endpoint_tolerance)
                self.assertTrue(report.settled)
                self.assertGreater(report.endpoint_error_m, .001)  # Do not substitute ideal FK.
                self.assertLessEqual(report.endpoint_error_m, .02)
                self.assertEqual(report.physics.obstacle_contacts + report.physics.self_contacts, 0)
                self.assertEqual(report.plan.scene_sha256, report.physics.scene_sha256)
                self.assertLessEqual(report.physics.maximum_actuator_torque_nm, 15)
                self.assertLessEqual(report.physics.maximum_measured_joint_rate_rad_s, .6)

    def test_absent_confirmation_never_requests_motion_or_claims_success(self):
        report = run_hand_target(TARGET)
        self.assertFalse(report.target_reached)
        self.assertEqual(report.physics.stop_reason, 'simulation_not_confirmed')
        self.assertTrue(all(value == 0 for value in report.physics.final_joints_rad.values()))
        # Even a target already at the neutral endpoint is not approved execution.
        neutral = run_hand_target((0, .22, .87))
        self.assertTrue(neutral.within_endpoint_tolerance)
        self.assertFalse(neutral.target_reached)

    def test_early_budget_does_not_claim_reach(self):
        report = run_hand_target(TARGET, steps=10, confirm_simulation=True)
        self.assertFalse(report.target_reached)
        self.assertFalse(report.within_endpoint_tolerance)
        self.assertGreater(report.endpoint_error_m, .1)

    def test_policy_and_reserve_stops_remain_latched_and_unsuccessful(self):
        for scenario in ('static_obstacle', 'living_obstacle', 'obstacle_intrusion', 'sensor_dropout', 'uncertain_sensor'):
            with self.subTest(scenario=scenario):
                report = run_hand_target(TARGET, scenario=scenario, confirm_simulation=True)
                self.assertFalse(report.target_reached)
                self.assertIsNotNone(report.physics.stop_reason)
                self.assertEqual(report.physics.obstacle_contacts + report.physics.self_contacts, 0)
                held = [row for row in report.physics.trace if row['stop_reason']]
                self.assertEqual(held[0]['joint_targets_rad'], held[-1]['joint_targets_rad'])

    def test_expected_contact_cannot_be_reported_as_reach_success(self):
        report = run_hand_target(TARGET, scenario='unavoidable_overlap', confirm_simulation=True)
        self.assertEqual(report.physics.terminal_reason, 'contact_detected')
        self.assertGreater(report.physics.obstacle_contacts, 0)
        self.assertFalse(report.target_reached)

    def test_reports_are_bounded_serializable_and_reproducible(self):
        first = run_hand_target(TARGET, steps=20, confirm_simulation=True)
        second = run_hand_target(TARGET, steps=20, confirm_simulation=True)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertNotIn('trace', first.to_dict()['physics'])
        self.assertEqual(len(first.to_dict(include_trace=True)['physics']['trace']), 20)
        json.dumps(first.to_dict(), allow_nan=False)

    def test_cli_preview_and_confirmed_execution(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        command = [sys.executable, '-m', 'jace.cli', 'simulate-reach', '--target', *map(str, TARGET)]
        preview = subprocess.run([*command, '--plan-only'], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(preview.stdout)['dynamics_executed'])
        executed = subprocess.run([*command, '--confirm-simulation'], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(executed.stdout)['target_reached'])
        invalid = subprocess.run([*command, '--target', '2', '.22', '1'], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, '')
        self.assertIn('outside the geometric reach', invalid.stderr)
