"""Optional real MuJoCo loop for a deliberately minimal simulation-only scene.

No viewer, network, external model/XML loader, ROS publisher or hardware path is
provided. Scenario labels are perfect synthetic annotations, not perception.
"""
from __future__ import annotations

import math
import hashlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .simulator import decide_motion

SCENARIOS = ('clear_path', 'static_obstacle', 'living_obstacle', 'obstacle_intrusion', 'sensor_dropout', 'uncertain_sensor')
SENSOR_RANGE_M = 4.0
MAX_STEPS = 2000
CLEARANCE_RESERVE_M = 0.02  # Fixture-specific reserve, not a general braking guarantee.


@dataclass(frozen=True)
class PhysicsReport:
    scenario: str
    backend_version: str
    simulation_confirmed: bool
    steps: int
    elapsed_simulation_s: float
    final_position_m: float
    final_velocity_m_s: float
    travelled_distance_m: float
    minimum_clearance_m: float
    obstacle_contacts: int
    action_counts: dict[str, int]
    terminal_reason: str
    controller_stop_reasons: dict[str, int]
    scene_sha256: str
    hardware_enabled: bool = False
    scene: str = 'original one-axis slider fixture; not a humanoid'
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_trace:
            result.pop('trace')
        return result


def run_physics_scenario(scenario: str = 'clear_path', *, steps: int = 500,
                         confirm_simulation: bool = False) -> PhysicsReport:
    """Advance real physics, applying bounded controls only with explicit opt-in.

    Confirmation is for this simulated episode only. Policy decisions keep
    executable=False/requires_confirmation=True and cannot reach hardware.
    """
    if scenario not in SCENARIOS:
        raise ValueError('unknown physics scenario')
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f'steps must be an integer between 1 and {MAX_STEPS}')
    if not isinstance(confirm_simulation, bool):
        raise ValueError('confirm_simulation must be boolean')
    try:
        import mujoco
    except ImportError:
        raise RuntimeError("MuJoCo is not installed. Install the optional simulation dependency; no mock simulation was run.") from None

    # Only the original packaged fixture is admitted. No caller-controlled XML,
    # plugin, asset path or callback can be supplied through this interface.
    scene = Path(__file__).with_name('data') / 'slider_scene.xml'
    scene_text = scene.read_text(encoding='utf-8')
    model = mujoco.MjModel.from_xml_string(scene_text)
    data = mujoco.MjData(model)
    robot = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'robot')
    obstacle = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'obstacle')
    if scenario in {'static_obstacle', 'living_obstacle'}:
        data.mocap_pos[0, 0] = 1.2
    mujoco.mj_forward(model, data)

    actions: Counter[str] = Counter()
    controller_stops: Counter[str] = Counter()
    trace: list[dict[str, Any]] = []
    travelled = 0.0
    min_clearance = SENSOR_RANGE_M
    contacts = 0
    terminal = 'step_budget_reached'
    for step in range(steps):
        if scenario == 'obstacle_intrusion' and step == 100:
            # A known tagged obstacle enters the path with positive clearance.
            # This is scripted scene motion, not vision or life detection.
            data.mocap_pos[0, 0] = float(data.qpos[0]) + 0.8
            mujoco.mj_forward(model, data)
        if not all(math.isfinite(float(value)) for value in (*data.qpos, *data.qvel)):
            data.ctrl[0] = 0.0
            raise RuntimeError('invalid physics state; simulation stopped')
        clearance = float(mujoco.mj_geomDistance(model, data, robot, obstacle, SENSOR_RANGE_M, None))
        if not math.isfinite(clearance):
            data.ctrl[0] = 0.0
            raise RuntimeError('invalid distance measurement; simulation stopped')
        min_clearance = min(min_clearance, clearance)
        observation: dict[str, Any] = {
            'distance_m': max(0.0, clearance),
            'living_entity': scenario == 'living_obstacle' or (scenario == 'obstacle_intrusion' and step >= 100),
            'fragile_object': False,
            'uncertainty': 0.8 if scenario == 'uncertain_sensor' else 0.0,
        }
        if scenario == 'sensor_dropout' and step >= 100:
            observation = {}
        decision = decide_motion(observation)
        actions[decision.action] += 1
        velocity = decision.velocity
        stop_reason = None
        if not confirm_simulation:
            stop_reason = 'simulation_not_confirmed'
        elif decision.action == 'HALT_AND_REROUTE':
            stop_reason = 'policy_halt'
        elif (decision.action not in {'PROCEED_SLOWLY', 'SLOW_AND_OBSERVE'}
              or decision.executable is not False or decision.requires_confirmation is not True
              or isinstance(velocity, bool) or not isinstance(velocity, (int, float))
              or not math.isfinite(velocity) or not 0 <= velocity <= 0.25):
            stop_reason = 'invalid_policy_command'
        elif clearance <= 0.5 + CLEARANCE_RESERVE_M:
            # Real dynamics have residual velocity after a zero target. This
            # small supervisor reserve is tested only for this fixed fixture.
            stop_reason = 'fixture_clearance_reserve'
        if stop_reason:
            velocity = 0.0
            controller_stops[stop_reason] += 1
        previous = float(data.qpos[0])
        data.ctrl[0] = velocity
        mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)  # Refresh geometry/contact state after integration.
        current = float(data.qpos[0])
        measured_velocity = float(data.qvel[0])
        if not math.isfinite(current) or not math.isfinite(measured_velocity):
            data.ctrl[0] = 0.0
            raise RuntimeError('invalid physics state; simulation stopped')
        travelled += abs(current - previous)
        after = float(mujoco.mj_geomDistance(model, data, robot, obstacle, SENSOR_RANGE_M, None))
        if not math.isfinite(after):
            data.ctrl[0] = 0.0
            raise RuntimeError('invalid distance measurement; simulation stopped')
        min_clearance = min(min_clearance, after)
        step_contacts = sum(1 for item in data.contact if {int(item.geom1), int(item.geom2)} == {robot, obstacle})
        contacts += step_contacts
        trace.append({
            'step': step, 'simulation_time_s': float(data.time), 'observation': observation,
            'decision': decision.to_dict(), 'simulated_velocity_target_m_s': velocity,
            'controller_stop_reason': stop_reason,
            'position_m': current, 'velocity_m_s': measured_velocity,
            'clearance_after_m': after, 'obstacle_contacts': step_contacts,
        })
        if step_contacts or after < 0:
            terminal = 'obstacle_contact_detected'
            break

    # Do not leave a nonzero control in a completed local simulation instance.
    data.ctrl[0] = 0.0
    return PhysicsReport(
        scenario=scenario, backend_version=mujoco.__version__, simulation_confirmed=confirm_simulation,
        steps=len(trace), elapsed_simulation_s=float(data.time), final_position_m=float(data.qpos[0]),
        final_velocity_m_s=float(data.qvel[0]), travelled_distance_m=travelled, minimum_clearance_m=min_clearance,
        obstacle_contacts=contacts, action_counts=dict(actions), terminal_reason=terminal,
        controller_stop_reasons=dict(controller_stops), scene_sha256=hashlib.sha256(scene_text.encode('utf-8')).hexdigest(),
        trace=trace,
    )
