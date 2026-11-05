"""Capped worker sharing model verification and guards across simulation experiments."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import sys


NUMERICAL_WARNINGS = ('mjWARN_BADQPOS', 'mjWARN_BADQVEL', 'mjWARN_BADQACC', 'mjWARN_BADCTRL')


def _numerical_guard_reason(warnings: dict[str, int], actual_time: float, expected_time: float) -> str | None:
    # MuJoCo may reset an unstable state to finite values. Finiteness alone is
    # insufficient evidence that no numerical failure happened during a step.
    if any(warnings.values()):
        return 'numerical_warning_guard_triggered'
    if not math.isfinite(actual_time) or abs(actual_time - expected_time) > 1e-8:
        return 'simulation_time_guard_triggered'
    return None


def _apply_resource_limits() -> None:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))


def _run(scenario: str, steps: int, include_trace: bool, *, confirm_simulation: bool = False,
         controller: str = 'source_servo') -> dict:
    if confirm_simulation is not True:
        raise ValueError('explicit simulation confirmation is required')
    from .freebase import SCENARIOS, MAX_STEPS
    if controller == 'contact_gait':
        from .freebase_gait import (SCENARIOS, DISTURBANCES, CONTROLLER_ID, ControllerFeasibilityError,
                                    validate_gait_runtime, validate_gait_backend_versions)
    elif controller == 'posture_feedback':
        from .freebase_balance import SCENARIOS, DISTURBANCES, CONTROLLER_ID
    elif controller != 'source_servo':
        raise ValueError('unknown free-base controller')
    if scenario not in SCENARIOS or type(steps) is not int or not 1 <= steps <= MAX_STEPS or type(include_trace) is not bool:
        raise ValueError('invalid internal simulation scenario or budget')
    if controller == 'contact_gait':
        validate_gait_runtime()
    import resource
    import mujoco
    if controller == 'contact_gait':
        import numpy
        validate_gait_backend_versions(getattr(mujoco, '__version__', 'unknown'),
                                       getattr(numpy, '__version__', 'unknown'))
    from .simulator import decide_motion
    directory = Path(__file__).with_name('data')
    provenance = json.loads((directory / 'unitree_g1_source.json').read_text())
    if set(provenance['runtime_sha256']) != {'unitree_g1_headless.xml', 'unitree_g1_scene.xml'}:
        raise RuntimeError('incomplete packaged model manifest')
    for name, expected in provenance['runtime_sha256'].items():
        if name not in {'unitree_g1_headless.xml', 'unitree_g1_scene.xml'}:
            raise RuntimeError('unexpected packaged model path')
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('packaged diagnostic model hash mismatch')
    model = mujoco.MjModel.from_xml_path(str(directory / 'unitree_g1_scene.xml'))
    if (model.nq, model.nv, model.nu) != (36, 35, 29) or model.jnt_type[0] != mujoco.mjtJoint.mjJNT_FREE:
        raise RuntimeError('unexpected diagnostic model topology')
    if not all(model.actuator_forcelimited):
        raise RuntimeError('diagnostic actuators lack source force limits')
    data = mujoco.MjData(model)
    home = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, 'home')
    pelvis = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'pelvis')
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'floor')
    feet = {mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f'{side}_foot{i}_collision')
            for side in ('left', 'right') for i in (1, 2, 3)}
    if min(home, pelvis, floor, *feet) < 0:
        raise RuntimeError('diagnostic model is missing a required named component')
    mujoco.mj_resetDataKeyframe(model, data, home)
    if scenario == 'initial_tilt':
        data.qpos[3:7] = [math.cos(.4), 0, math.sin(.4), 0]  # 0.8 rad initial tilt.
    mujoco.mj_forward(model, data)
    feedback = None
    if controller == 'contact_gait':
        from .freebase_gait_controller import ContactGaitPrototype
        feedback = ContactGaitPrototype(model, data)
    elif controller == 'posture_feedback':
        from .freebase_balance_controller import PostureFeedback
        feedback = PostureFeedback(model, data)
    initial_root_position = [float(v) for v in data.qpos[:3]]
    settled_steps = 0
    minimum_height = float(data.qpos[2])
    maximum_tilt = maximum_torque = maximum_joint_rate = 0.0
    max_foot_contacts = nonfoot_contacts = self_contacts = 0
    completed = 0
    terminal = 'step_budget_reached'
    controller_failure = None
    trace = []

    def numerical_warnings() -> dict[str, int]:
        return {name: int(data.warning[getattr(mujoco.mjtWarning, name)].number)
                for name in NUMERICAL_WARNINGS}

    def observe() -> tuple[dict, str | None]:
        nonlocal minimum_height, maximum_tilt, maximum_torque, maximum_joint_rate
        nonlocal max_foot_contacts, nonfoot_contacts, self_contacts
        if not all(math.isfinite(float(value)) for value in (*data.qpos, *data.qvel, *data.actuator_force)):
            raise RuntimeError('nonfinite diagnostic state; run stopped')
        if abs(sum(float(v)**2 for v in data.qpos[3:7]) - 1) > 1e-6:
            raise RuntimeError('invalid root orientation; run stopped')
        height = float(data.qpos[2])
        tilt = math.acos(max(-1.0, min(1.0, 1 - 2 * (float(data.qpos[4])**2 + float(data.qpos[5])**2))))
        minimum_height = min(minimum_height, height)
        maximum_tilt = max(maximum_tilt, tilt)
        maximum_torque = max(maximum_torque, max(abs(float(v)) for v in data.actuator_force))
        rate = max(abs(float(v)) for v in data.qvel[6:])
        maximum_joint_rate = max(maximum_joint_rate, rate)
        foot = nonfoot = self_count = 0
        for contact in data.contact:
            pair = {int(contact.geom1), int(contact.geom2)}
            if floor in pair:
                if pair & feet:
                    foot += 1
                else:
                    nonfoot += 1
            else:
                self_count += 1
        max_foot_contacts = max(max_foot_contacts, foot)
        nonfoot_contacts += nonfoot
        self_contacts += self_count
        reason = _numerical_guard_reason(numerical_warnings(), float(data.time),
                                         completed * float(model.opt.timestep))
        if reason:
            pass
        elif height < .55 or tilt > .5:
            reason = 'posture_guard_triggered'
        elif nonfoot or self_count:
            reason = 'unexpected_contact_detected'
        elif rate > 20:
            reason = 'joint_rate_guard_triggered'
        elif any(abs(float(force)) > max(abs(float(low)), abs(float(high))) + 1e-6
                 for force, (low, high) in zip(data.actuator_force, model.actuator_forcerange)):
            reason = 'actuator_force_guard_triggered'
        return {'simulation_time_s': float(data.time), 'pelvis_height_m': height, 'tilt_rad': tilt,
                'foot_contact_points': foot, 'nonfoot_floor_contacts': nonfoot, 'self_contacts': self_count}, reason

    initial, reason = observe()
    if reason:
        terminal = reason
    else:
        for step in range(steps):
            if scenario == 'sensor_dropout' and step >= 100:
                if decide_motion({}).action != 'HALT_AND_REROUTE':
                    raise RuntimeError('invalid missing-sensor policy result')
                terminal = 'sensor_guard_triggered'
                break
            data.xfrc_applied[:] = 0
            if feedback is not None:
                disturbance = DISTURBANCES[scenario]
                if disturbance is not None and disturbance[0] <= step < disturbance[1]:
                    data.xfrc_applied[pelvis, :3] = disturbance[2]
                if controller == 'contact_gait':
                    try:
                        data.ctrl[:] = feedback.command(data)
                    except ControllerFeasibilityError as error:
                        terminal = 'controller_feasibility_guard_triggered'
                        controller_failure = str(error)
                        break
                else:
                    data.ctrl[:] = feedback.command(data)
            elif 100 <= step < 125 and scenario in {'forward_push', 'lateral_push'}:
                data.xfrc_applied[pelvis, 0 if scenario == 'forward_push' else 1] = 100
            # Diagnostic retains source targets; balance only changes bounded ctrl.
            # Neither path changes root state, model, gravity, contacts or support.
            mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)
            completed += 1
            state, reason = observe()
            if feedback is not None:
                linear_speed = math.sqrt(sum(float(v)**2 for v in data.qvel[:3]))
                angular_speed = math.sqrt(sum(float(v)**2 for v in data.qvel[3:6]))
                joint_speed = max(abs(float(v)) for v in data.qvel[6:])
                settled_steps = settled_steps + 1 if (linear_speed < .05 and angular_speed < .1
                    and joint_speed < .1 and state['tilt_rad'] < .1) else 0
                state.update(root_speed_m_s=linear_speed, root_angular_speed_rad_s=angular_speed,
                             maximum_joint_rate_rad_s=joint_speed)
            if include_trace:
                trace.append({'step': completed, **state, 'terminal_reason': reason})
            if reason:
                terminal = reason
                break
    result = {'schema': 'jace.freebase.diagnostic.v1', 'scenario': scenario,
              'scope': 'Modified free-base model with source neutral position servos; not validated standing, balance, locomotion or hardware safety',
              'backend_version': mujoco.__version__, 'simulation_confirmed': True,
              'steps': completed, 'elapsed_simulation_s': float(data.time), 'terminal_reason': terminal,
              'no_guard_triggered_within_horizon': terminal == 'step_budget_reached',
              'standing_verified': False, 'locomotion_controller': False, 'pretrained_policy_loaded': False,
              'hardware_enabled': False, 'free_base': True, 'actuated_joints': model.nu,
              'mass_kg': float(sum(model.body_mass)), 'minimum_pelvis_height_m': minimum_height,
              'maximum_tilt_rad': maximum_tilt, 'maximum_joint_rate_rad_s': maximum_joint_rate,
              'maximum_actuator_force_nm': maximum_torque, 'maximum_foot_contact_points': max_foot_contacts,
              'nonfoot_floor_contact_observations': nonfoot_contacts, 'self_contact_observations': self_contacts,
              'final_root_position_m': [float(v) for v in data.qpos[:3]],
              'source_commit': provenance['source_commit'], 'modified_model_sha256': provenance['runtime_sha256'],
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'resource_limits': {'address_space_bytes': resource.getrlimit(resource.RLIMIT_AS)[0],
                                  'cpu_seconds': resource.getrlimit(resource.RLIMIT_CPU)[0]},
              'initial_observation': initial, 'numerical_warning_counts': numerical_warnings()}
    if feedback is not None:
        result.update(
            schema='jace.freebase.balance.v1', controller_id=CONTROLLER_ID,
            controller_sha256=hashlib.sha256(Path(__file__).with_name('freebase_balance_controller.py').read_bytes()).hexdigest(),
            scope='Finite-horizon free-base posture feedback experiment, not full balance qualification or walking',
            walking_verified=False, balance_qualified=False, external_support_enabled=False,
            controller_uses_exact_simulator_state=True, root_state_written_during_episode=False,
            initial_root_position_m=initial_root_position,
            final_root_linear_velocity_m_s=[float(v) for v in data.qvel[:3]],
            final_root_angular_velocity_rad_s=[float(v) for v in data.qvel[3:6]],
            final_joint_rate_rad_s=max(abs(float(v)) for v in data.qvel[6:]),
            settled_tail_s=settled_steps * float(model.opt.timestep),
            finite_horizon_posture_accepted=(terminal == 'step_budget_reached' and steps == MAX_STEPS
                                            and settled_steps >= 250),
            target_clipping_observations=feedback.clipped_target_observations,
            maximum_target_delta_rad=feedback.maximum_target_delta_rad,
            disturbance=(None if DISTURBANCES[scenario] is None else {
                'start_step': DISTURBANCES[scenario][0], 'end_step_exclusive': DISTURBANCES[scenario][1],
                'pelvis_force_world_n': list(DISTURBANCES[scenario][2])}))
    if controller == 'contact_gait':
        result.update(feedback.probe_report(data, include_trace=include_trace))
        result.update(
            schema='jace.freebase.gait_probe.v1', locomotion_controller=True,
            controller_status='experimental_two_step_only',
            scope='Experimental two-step finite-horizon simulation, not general walking or balance qualification',
            controller_sha256=hashlib.sha256(Path(__file__).with_name('freebase_gait_controller.py').read_bytes()).hexdigest(),
            controller_failure_detail=controller_failure,
            two_step_probe_accepted=(result['finite_horizon_posture_accepted']
                                    and result['two_step_sequence_observed']
                                    and result['last_second_double_support_observed']))
    if include_trace:
        result['trace'] = trace
    return result


def main() -> int:
    _apply_resource_limits()
    from .freebase import SCENARIOS, MAX_STEPS
    try:
        if (len(sys.argv) != 5 or sys.argv[1] not in SCENARIOS or sys.argv[3] not in {'trace', 'summary'}
            or sys.argv[4] != '--confirmed-simulation'):
            raise ValueError('invalid internal diagnostic arguments')
        steps = int(sys.argv[2])
        if not 1 <= steps <= MAX_STEPS:
            raise ValueError('invalid internal diagnostic step budget')
        result = _run(sys.argv[1], steps, sys.argv[3] == 'trace', confirm_simulation=True)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ImportError, RuntimeError, ValueError, MemoryError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
