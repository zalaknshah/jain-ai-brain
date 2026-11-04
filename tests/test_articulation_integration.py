import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.articulated import JOINTS, run_articulation_scenario
from jace.simulator import SimulationDecision, decide_motion


class ArticulationContractTests(unittest.TestCase):
    def test_invalid_configuration_is_rejected(self):
        for options in ({'steps':0},{'steps':2001},{'steps':True},{'confirm_simulation':'true'},{'scenario':'custom.xml'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                run_articulation_scenario(**options)


@unittest.skipUnless(importlib.util.find_spec('mujoco'), 'Optional MuJoCo dependency missing; real articulation test not run')
class RealArticulationTests(unittest.TestCase):
    def test_original_fixture_has_fixed_base_radian_ranges_and_bounded_actuators(self):
        import mujoco
        from jace import articulated
        path=Path(articulated.__file__).with_name('data')/'articulated_scene.xml'
        model=mujoco.MjModel.from_xml_string(path.read_text())
        self.assertEqual((model.nq,model.nv,model.nu),(9,9,9))
        self.assertTrue(all(kind==mujoco.mjtJoint.mjJNT_HINGE for kind in model.jnt_type))
        shoulder=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_JOINT,'left_shoulder')
        self.assertAlmostEqual(model.jnt_range[shoulder,1],.65)
        self.assertTrue(all(low==-15 and high==15 for low,high in model.actuator_forcerange))
        self.assertAlmostEqual(model.opt.gravity[2],-9.81)

    def test_clear_path_moves_real_articulated_joints_without_contact(self):
        report=run_articulation_scenario(steps=1000,confirm_simulation=True)
        self.assertEqual(report.steps,1000)
        self.assertEqual(report.terminal_reason,'step_budget_reached')
        self.assertGreater(report.final_joints_rad['left_shoulder'],.5)
        self.assertGreater(report.final_joints_rad['left_elbow'],.6)
        self.assertGreater(report.final_hand_position_m[0],.3)
        self.assertLessEqual(report.maximum_measured_joint_rate_rad_s,.6)
        self.assertLessEqual(report.maximum_actuator_torque_nm,15)
        self.assertEqual(report.obstacle_contacts+report.self_contacts,0)
        self.assertTrue(report.fixed_base); self.assertFalse(report.hardware_enabled)
        self.assertEqual(set(report.final_joints_rad),set(JOINTS))
        previous={name:0 for name in JOINTS}
        for row in report.trace:
            self.assertFalse(row['decision']['executable'])
            self.assertTrue(row['decision']['requires_confirmation'])
            for name,value in row['joint_targets_rad'].items():
                self.assertLessEqual(abs(value-previous[name]),.2*.005+1e-10)
            previous=row['joint_targets_rad']

    def test_confirmation_absent_or_initial_halt_has_no_posture_transition(self):
        for scenario,confirmed in [('clear_path',False),('living_obstacle',True),('uncertain_sensor',True)]:
            with self.subTest(scenario=scenario,confirmed=confirmed):
                report=run_articulation_scenario(scenario,steps=300,confirm_simulation=confirmed)
                self.assertTrue(all(abs(value)<1e-12 for value in report.final_joints_rad.values()))
                self.assertEqual(report.obstacle_contacts+report.self_contacts,0)
                self.assertIsNotNone(report.stop_reason)

    def test_static_obstacle_latches_hold_above_half_metre_clearance(self):
        report=run_articulation_scenario('static_obstacle',steps=1000,confirm_simulation=True)
        self.assertEqual(report.stop_reason,'fixture_clearance_reserve')
        self.assertGreaterEqual(report.minimum_clearance_m,.5)
        self.assertTrue(all(abs(value)<1e-6 for value in report.final_joint_velocities_rad_s.values()))
        self.assertLess(report.final_joints_rad['left_shoulder'],.3)
        self.assertEqual(report.obstacle_contacts+report.self_contacts,0)

    def test_intrusion_and_sensor_loss_stop_and_hold(self):
        for scenario in ('obstacle_intrusion','sensor_dropout'):
            with self.subTest(scenario=scenario):
                report=run_articulation_scenario(scenario,steps=1000,confirm_simulation=True)
                self.assertIsNone(report.trace[199]['stop_reason'])
                self.assertEqual(report.trace[200]['stop_reason'],'policy_halt')
                self.assertEqual(report.trace[200]['joint_targets_rad'],report.trace[-1]['joint_targets_rad'])
                self.assertTrue(all(abs(value)<1e-6 for value in report.final_joint_velocities_rad_s.values()))
                self.assertGreaterEqual(report.minimum_clearance_m,.5)
                self.assertEqual(report.obstacle_contacts+report.self_contacts,0)

    def test_recovered_observation_does_not_automatically_restart_motion(self):
        calls=[0]
        def transient_halt(observation):
            calls[0]+=1
            return decide_motion({}) if calls[0]==201 else decide_motion(observation)
        with patch('jace.articulated.decide_motion',side_effect=transient_halt):
            report=run_articulation_scenario(steps=600,confirm_simulation=True)
        self.assertEqual(report.trace[-1]['decision']['action'],'PROCEED_SLOWLY')
        self.assertEqual(report.trace[-1]['stop_reason'],'policy_halt')
        self.assertEqual(report.trace[200]['joint_targets_rad'],report.trace[-1]['joint_targets_rad'])

    def test_invalid_policy_contract_cannot_start_posture_transition(self):
        invalid=[SimulationDecision('OTHER','fixture',.25,1),SimulationDecision('PROCEED_SLOWLY','fixture',float('nan'),1),
                 SimulationDecision('PROCEED_SLOWLY','fixture',.25,1,False,True)]
        for decision in invalid:
            with self.subTest(decision=decision),patch('jace.articulated.decide_motion',return_value=decision):
                report=run_articulation_scenario(steps=10,confirm_simulation=True)
                self.assertEqual(report.stop_reason,'invalid_policy_command')
                self.assertTrue(all(value==0 for value in report.final_joints_rad.values()))

    def test_one_nonfinite_link_measurement_cannot_be_hidden_by_minimum(self):
        calls=[0]
        def one_invalid(*args):
            calls[0]+=1
            return float('nan') if calls[0]==2 else 3.0
        with patch('mujoco.mj_geomDistance',side_effect=one_invalid):
            with self.assertRaisesRegex(RuntimeError,'invalid geometry distance'):
                run_articulation_scenario(steps=10,confirm_simulation=True)

    def test_unavoidable_overlap_is_reported_as_contact_not_success(self):
        report=run_articulation_scenario('unavoidable_overlap',steps=1000,confirm_simulation=True)
        self.assertEqual(report.terminal_reason,'contact_detected')
        self.assertLess(report.steps,1000)
        self.assertLess(report.minimum_clearance_m,0)
        self.assertGreater(report.obstacle_contacts,0)

    def test_nonadjacent_self_collision_is_reported_not_filtered_out(self):
        from jace import articulated
        scene=(Path(articulated.__file__).with_name('data')/'articulated_scene.xml').read_text()
        # Compile a test-only colliding copy so MuJoCo also recomputes broadphase
        # geometry bounds; no production file or loader option is changed.
        scene=scene.replace('name="right_hand_geom" type="sphere" pos="0 0 -0.25"',
                            'name="right_hand_geom" type="sphere" pos="0 0.44 -0.25"')
        with patch('jace.articulated.Path.read_text',return_value=scene):
            report=run_articulation_scenario(steps=10,confirm_simulation=True)
        self.assertEqual(report.terminal_reason,'contact_detected')
        self.assertGreater(report.self_contacts,0)

    def test_repeated_runs_are_reproducible(self):
        first=run_articulation_scenario(steps=100,confirm_simulation=True)
        second=run_articulation_scenario(steps=100,confirm_simulation=True)
        self.assertEqual(first.to_dict(include_trace=True),second.to_dict(include_trace=True))
