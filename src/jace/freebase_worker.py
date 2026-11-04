"""Internal capped worker. Source position servos only, deliberately no gait controller."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import sys


def _apply_resource_limits() -> None:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))


def _run(scenario: str, steps: int, include_trace: bool, *, confirm_simulation: bool = False) -> dict:
    if confirm_simulation is not True:
        raise ValueError('explicit simulation confirmation is required')
    import resource
    import mujoco
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
    minimum_height = float(data.qpos[2])
    maximum_tilt = maximum_torque = maximum_joint_rate = 0.0
    max_foot_contacts = nonfoot_contacts = self_contacts = 0
    completed = 0
    terminal = 'step_budget_reached'
    trace = []

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
        reason = None
        if height < .55 or tilt > .5:
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
            if 100 <= step < 125 and scenario in {'forward_push', 'lateral_push'}:
                data.xfrc_applied[pelvis, 0 if scenario == 'forward_push' else 1] = 100
            # Keep the source home position targets. No learned policy or gait.
            mujoco.mj_step(model, data)
            mujoco.mj_forward(model, data)
            completed += 1
            state, reason = observe()
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
              'initial_observation': initial}
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
