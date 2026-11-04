"""Original anchored articulation fixture. No free-base balance, gait or hardware."""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .physics import MAX_STEPS, SCENARIOS, SENSOR_RANGE_M
from .simulator import decide_motion

ARTICULATION_SCENARIOS = (*SCENARIOS, 'unavoidable_overlap')

JOINTS = ('neck', 'left_shoulder', 'left_elbow', 'right_shoulder', 'right_elbow',
          'left_hip', 'left_knee', 'right_hip', 'right_knee')
CLEARANCE_STOP_M = 0.55  # Tested reserve for this original fixed fixture only.
TARGET_RATE_RAD_S = 0.2
MAX_MEASURED_RATE_RAD_S = 0.6


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class ArticulationReport:
    scenario: str
    backend_version: str
    simulation_confirmed: bool
    steps: int
    elapsed_simulation_s: float
    final_joints_rad: dict[str, float]
    final_joint_velocities_rad_s: dict[str, float]
    final_hand_position_m: list[float]
    minimum_clearance_m: float
    maximum_measured_joint_rate_rad_s: float
    maximum_actuator_torque_nm: float
    obstacle_contacts: int
    self_contacts: int
    stop_reason: str | None
    terminal_reason: str
    policy_action_counts: dict[str, int]
    scene_sha256: str
    fixed_base: bool = True
    hardware_enabled: bool = False
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_trace:
            result.pop('trace')
        return result


def run_articulation_scenario(scenario: str = 'clear_path', *, steps: int = 1000,
                              confirm_simulation: bool = False,
                              left_arm_target_rad: tuple[float, float] | None = None) -> ArticulationReport:
    if scenario not in ARTICULATION_SCENARIOS:
        raise ValueError('unknown articulation scenario')
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f'steps must be an integer between 1 and {MAX_STEPS}')
    if not isinstance(confirm_simulation, bool):
        raise ValueError('confirm_simulation must be boolean')
    if left_arm_target_rad is not None:
        if (not isinstance(left_arm_target_rad, (list, tuple)) or len(left_arm_target_rad) != 2
            or any(not _is_finite_number(value) for value in left_arm_target_rad)):
            raise ValueError('left_arm_target_rad must contain two finite numbers')
        if not -.1 <= left_arm_target_rad[0] <= .65 or not 0 <= left_arm_target_rad[1] <= .9:
            raise ValueError('left arm target exceeds fixture joint limits')
    try:
        import mujoco
    except ImportError:
        raise RuntimeError('MuJoCo is unavailable; install the optional simulation dependency. No mock was run.') from None
    scene_text = (Path(__file__).with_name('data') / 'articulated_scene.xml').read_text(encoding='utf-8')
    model = mujoco.MjModel.from_xml_string(scene_text)
    data = mujoco.MjData(model)
    if model.nq != len(JOINTS) or model.nv != len(JOINTS) or model.nu != len(JOINTS):
        raise RuntimeError('unexpected articulated fixture topology')
    ids = {name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in JOINTS}
    if any(joint < 0 for joint in ids.values()):
        raise RuntimeError('articulated fixture is missing a required joint')
    addresses = {name: int(model.jnt_qposadr[joint]) for name, joint in ids.items()}
    dofs = {name: int(model.jnt_dofadr[joint]) for name, joint in ids.items()}
    actuators = {name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) for name in JOINTS}
    if any(actuator < 0 for actuator in actuators.values()):
        raise RuntimeError('articulated fixture is missing a required actuator')
    obstacle = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'obstacle')
    hand = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'left_hand_geom')
    robot_geoms = {index for index in range(model.ngeom) if mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, index).endswith('_geom')}
    if scenario in {'static_obstacle', 'living_obstacle'}:
        data.mocap_pos[0] = [0.85, 0.22, 1.05]
    mujoco.mj_forward(model, data)
    targets = {name: float(data.qpos[address]) for name, address in addresses.items()}
    shoulder, elbow = left_arm_target_rad if left_arm_target_rad is not None else (.55, .65)
    desired = dict(targets, left_shoulder=shoulder, left_elbow=elbow)
    if any(not float(model.jnt_range[ids[name], 0]) <= value <= float(model.jnt_range[ids[name], 1])
           or not float(model.actuator_ctrlrange[actuators[name], 0]) <= value <= float(model.actuator_ctrlrange[actuators[name], 1])
           for name, value in desired.items()):
        raise RuntimeError('desired posture exceeds packaged fixture limits')
    stop_reason = None if confirm_simulation else 'simulation_not_confirmed'
    terminal = 'step_budget_reached'
    minimum = SENSOR_RANGE_M
    max_rate = max_torque = 0.0
    obstacle_contacts = self_contacts = 0
    actions: Counter[str] = Counter()
    trace: list[dict[str, Any]] = []

    def clearance() -> float:
        distances = [float(mujoco.mj_geomDistance(model, data, geom, obstacle, SENSOR_RANGE_M, None)) for geom in robot_geoms]
        if not distances or not all(math.isfinite(value) for value in distances):
            raise RuntimeError('invalid geometry distance; articulated simulation stopped')
        return min(distances)

    for step in range(steps):
        if not all(math.isfinite(float(value)) for value in (*data.qpos, *data.qvel)):
            raise RuntimeError('invalid articulated physics state; simulation stopped')
        if scenario in {'obstacle_intrusion', 'unavoidable_overlap'} and step == 200:
            # The overlap case is intentionally impossible to avoid: validate
            # honest contact/failure reporting, not a success/safety claim.
            offset = 0.05 if scenario == 'unavoidable_overlap' else 0.8
            data.mocap_pos[0] = data.geom_xpos[hand] + [offset, 0.0, 0.0]
            mujoco.mj_forward(model, data)
        distance = clearance()
        minimum = min(minimum, distance)
        observation: dict[str, Any] = {
            'distance_m': max(0.0, distance),
            'living_entity': scenario == 'living_obstacle' or (scenario in {'obstacle_intrusion', 'unavoidable_overlap'} and step >= 200),
            'fragile_object': False,
            'uncertainty': 0.8 if scenario == 'uncertain_sensor' else 0.0,
        }
        if scenario == 'sensor_dropout' and step >= 200:
            observation = {}
        decision = decide_motion(observation)
        actions[decision.action] += 1
        new_stop = None
        if decision.action == 'HALT_AND_REROUTE':
            new_stop = 'policy_halt'
        elif (decision.action not in {'PROCEED_SLOWLY', 'SLOW_AND_OBSERVE'}
              or decision.executable is not False or decision.requires_confirmation is not True
              or isinstance(decision.velocity, bool) or not isinstance(decision.velocity, (int, float))
              or not math.isfinite(decision.velocity) or not 0 <= decision.velocity <= 0.25):
            new_stop = 'invalid_policy_command'
        elif distance <= CLEARANCE_STOP_M:
            new_stop = 'fixture_clearance_reserve'
        if stop_reason is None and new_stop:
            stop_reason = new_stop
            # Capture a fixed hold posture once. Continuously copying qpos would
            # allow gravity drift instead of holding against it. Never auto-resume.
            targets = {name: float(data.qpos[address]) for name, address in addresses.items()}
        if stop_reason is None:
            # Policy linear-speed hints are NOT treated as rad/s commands. This
            # separate, bounded joint-space profile belongs only to the fixture.
            rate = TARGET_RATE_RAD_S if decision.action == 'PROCEED_SLOWLY' else TARGET_RATE_RAD_S / 2
            increment = rate * float(model.opt.timestep)
            for name in JOINTS:
                error = desired[name] - targets[name]
                targets[name] += max(-increment, min(increment, error))
        for name in JOINTS:
            actuator = actuators[name]
            low, high = model.actuator_ctrlrange[actuator]
            targets[name] = max(float(low), min(float(high), targets[name]))
            data.ctrl[actuator] = targets[name]
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        if not all(math.isfinite(float(value)) for value in (*data.qpos, *data.qvel, *data.actuator_force)):
            raise RuntimeError('invalid articulated physics state; simulation stopped')
        after = clearance()
        minimum = min(minimum, after)
        velocities = {name: float(data.qvel[dof]) for name, dof in dofs.items()}
        joints = {name: float(data.qpos[address]) for name, address in addresses.items()}
        peak_rate = max(abs(value) for value in velocities.values())
        peak_torque = max(abs(float(value)) for value in data.actuator_force)
        max_rate = max(max_rate, peak_rate)
        max_torque = max(max_torque, peak_torque)
        obstacle_count = sum(1 for item in data.contact if obstacle in {int(item.geom1), int(item.geom2)})
        self_count = sum(1 for item in data.contact if int(item.geom1) in robot_geoms and int(item.geom2) in robot_geoms)
        obstacle_contacts += obstacle_count
        self_contacts += self_count
        trace.append({'step': step, 'simulation_time_s': float(data.time), 'observation': observation,
                      'decision': decision.to_dict(), 'joint_targets_rad': dict(targets),
                      'joints_rad': joints, 'joint_velocities_rad_s': velocities,
                      'clearance_after_m': after, 'stop_reason': stop_reason,
                      'obstacle_contacts': obstacle_count, 'self_contacts': self_count})
        if obstacle_count or self_count or distance < 0 or after < 0:
            terminal = 'contact_detected'
            break
        if peak_rate > MAX_MEASURED_RATE_RAD_S:
            terminal = 'joint_rate_bound_exceeded'
            break
        if any(not float(model.jnt_range[ids[name], 0]) - 0.02 <= value <= float(model.jnt_range[ids[name], 1]) + 0.02 for name, value in joints.items()):
            terminal = 'joint_range_bound_exceeded'
            break
    return ArticulationReport(
        scenario, mujoco.__version__, confirm_simulation, len(trace), float(data.time),
        {name: float(data.qpos[address]) for name, address in addresses.items()},
        {name: float(data.qvel[dof]) for name, dof in dofs.items()},
        [float(value) for value in data.geom_xpos[hand]], minimum, max_rate, max_torque,
        obstacle_contacts, self_contacts, stop_reason, terminal, dict(actions),
        hashlib.sha256(scene_text.encode('utf-8')).hexdigest(), trace=trace,
    )
