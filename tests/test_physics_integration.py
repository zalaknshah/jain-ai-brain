import importlib.util
import unittest
from unittest.mock import patch

from jace.physics import run_physics_scenario
from jace.simulator import SimulationDecision


class PhysicsContractTests(unittest.TestCase):
    def test_invalid_configuration_is_rejected_before_loading_backend(self):
        for options in ({'steps':0}, {'steps':2001}, {'steps':True}, {'steps':1.5}, {'confirm_simulation':1}, {'scenario':'external.xml'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_physics_scenario(**options)


@unittest.skipUnless(importlib.util.find_spec('mujoco'), 'Optional MuJoCo dependency is not installed; real physics test not run')
class RealPhysicsTests(unittest.TestCase):
    def test_clear_path_runs_actual_physics_with_bounded_controls(self):
        result = run_physics_scenario(steps=500, confirm_simulation=True)
        self.assertEqual(result.backend_version, '3.17.0')
        self.assertEqual(result.steps,500)
        self.assertAlmostEqual(result.elapsed_simulation_s,5.0)
        self.assertGreater(result.final_position_m,1.0)
        self.assertLessEqual(result.final_velocity_m_s,0.25)
        self.assertFalse(result.hardware_enabled)
        self.assertEqual(result.obstacle_contacts,0)
        self.assertEqual(len(result.scene_sha256),64)
        self.assertNotIn('trace',result.to_dict())
        self.assertEqual(len(result.to_dict(include_trace=True)['trace']),500)
        for row in result.trace:
            self.assertLessEqual(row['simulated_velocity_target_m_s'],0.25)
            self.assertFalse(row['decision']['executable'])
            self.assertTrue(row['decision']['requires_confirmation'])

    def test_absent_simulation_confirmation_never_applies_motion(self):
        result = run_physics_scenario(steps=200)
        self.assertEqual(result.final_position_m,0)
        self.assertEqual(result.travelled_distance_m,0)
        self.assertEqual(result.controller_stop_reasons,{'simulation_not_confirmed':200})

    def test_static_obstacle_preserves_measured_clearance_without_contact(self):
        result = run_physics_scenario('static_obstacle',steps=1000,confirm_simulation=True)
        self.assertGreater(result.final_position_m,0.4)
        self.assertGreaterEqual(result.minimum_clearance_m,0.5)
        self.assertAlmostEqual(result.final_velocity_m_s,0,places=8)
        self.assertEqual(result.obstacle_contacts,0)
        self.assertIn('fixture_clearance_reserve',result.controller_stop_reasons)
        self.assertLess(result.trace[-1]['observation']['distance_m'],result.trace[0]['observation']['distance_m'])

    def test_living_and_uncertain_synthetic_observations_stay_stopped(self):
        for scenario in ('living_obstacle','uncertain_sensor'):
            with self.subTest(scenario=scenario):
                result=run_physics_scenario(scenario,steps=200,confirm_simulation=True)
                self.assertEqual(result.final_position_m,0)
                self.assertEqual(result.action_counts,{'HALT_AND_REROUTE':200})
                self.assertEqual(result.obstacle_contacts,0)

    def test_intrusion_updates_real_geometry_and_stops(self):
        result=run_physics_scenario('obstacle_intrusion',steps=400,confirm_simulation=True)
        self.assertEqual(result.trace[99]['decision']['action'],'PROCEED_SLOWLY')
        self.assertTrue(result.trace[100]['observation']['living_entity'])
        self.assertEqual(result.trace[100]['decision']['action'],'HALT_AND_REROUTE')
        self.assertLess(result.trace[100]['observation']['distance_m'],1.0)
        self.assertEqual(result.obstacle_contacts,0)
        self.assertGreater(result.minimum_clearance_m,0.5)
        self.assertAlmostEqual(result.final_velocity_m_s,0,places=8)

    def test_sensor_loss_removes_reading_and_stops_actual_motion(self):
        result=run_physics_scenario('sensor_dropout',steps=400,confirm_simulation=True)
        self.assertEqual(result.trace[100]['observation'],{})
        self.assertEqual(result.trace[100]['simulated_velocity_target_m_s'],0)
        self.assertLess(result.final_position_m-result.trace[99]['position_m'],0.02)
        self.assertAlmostEqual(result.final_velocity_m_s,0,places=8)

    def test_invalid_policy_command_is_not_applied(self):
        for velocity in (100.0,float('nan'),True):
            decision=SimulationDecision('PROCEED_SLOWLY','fixture',velocity,1.0)
            with self.subTest(velocity=velocity), patch('jace.physics.decide_motion',return_value=decision):
                result=run_physics_scenario(steps=5,confirm_simulation=True)
                self.assertEqual(result.final_position_m,0)
                self.assertEqual(result.controller_stop_reasons,{'invalid_policy_command':5})

    def test_nonfinite_geometry_stops_with_error_not_a_success_report(self):
        with patch('mujoco.mj_geomDistance',return_value=float('nan')):
            with self.assertRaisesRegex(RuntimeError,'invalid distance measurement'):
                run_physics_scenario(steps=5,confirm_simulation=True)

    def test_repeated_runs_are_reproducible(self):
        first=run_physics_scenario('static_obstacle',steps=100,confirm_simulation=True)
        second=run_physics_scenario('static_obstacle',steps=100,confirm_simulation=True)
        self.assertEqual(first.to_dict(include_trace=True),second.to_dict(include_trace=True))
