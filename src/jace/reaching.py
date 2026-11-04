"""Bounded planar reaching for the original fixed-base fixture, never hardware."""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .articulated import ArticulationReport, _is_finite_number, run_articulation_scenario

# These dimensions are specific to the original asset, not generic robot data.
# Every solution is checked against actual MuJoCo forward kinematics and limits.
SHOULDER_M = (0.0, .22, 1.4)
UPPER_ARM_M = .28
FOREARM_M = .25
ENDPOINT_TOLERANCE_M = .02
SETTLED_RATE_RAD_S = .02


@dataclass(frozen=True)
class HandTargetPlan:
    target_m: tuple[float, float, float]
    shoulder_rad: float
    elbow_rad: float
    predicted_hand_m: tuple[float, float, float]
    kinematic_residual_m: float
    scene_sha256: str
    backend_version: str
    hardware_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReachReport:
    plan: HandTargetPlan
    physics: ArticulationReport
    endpoint_error_m: float
    within_endpoint_tolerance: bool
    settled: bool
    target_reached: bool
    endpoint_tolerance_m: float = ENDPOINT_TOLERANCE_M
    settled_rate_rad_s: float = SETTLED_RATE_RAD_S

    def to_dict(self, *, include_trace: bool = False) -> dict[str, Any]:
        result = asdict(self)
        result['physics'] = self.physics.to_dict(include_trace=include_trace)
        return result


def plan_hand_target(target_m: tuple[float, float, float]) -> HandTargetPlan:
    """Solve the allowed elbow branch, then verify against packaged kinematics.

    No dynamics steps or actuation occur during planning. This checks endpoint
    geometry only: it does not establish a collision-free path or reach under load.
    """
    if (not isinstance(target_m, (list, tuple)) or len(target_m) != 3
        or any(not _is_finite_number(value) for value in target_m)):
        raise ValueError('target_m must contain three finite numbers in world metres')
    target = tuple(float(value) for value in target_m)
    if abs(target[1] - SHOULDER_M[1]) > 1e-10:
        raise ValueError('target is outside the fixed left-arm plane (y = 0.22 m)')
    x, down = target[0] - SHOULDER_M[0], SHOULDER_M[2] - target[2]
    radius = math.hypot(x, down)
    if radius > UPPER_ARM_M + FOREARM_M + 1e-12 or radius < abs(UPPER_ARM_M - FOREARM_M) - 1e-12:
        raise ValueError('target is outside the geometric reach of this arm')
    cosine = (radius * radius - UPPER_ARM_M**2 - FOREARM_M**2) / (2 * UPPER_ARM_M * FOREARM_M)
    # Clamp floating-point roundoff only, after the explicit reach test above.
    # acos is ill-conditioned at a straight arm: exact boundary targets can
    # otherwise acquire a spurious ~1e-8 rad elbow and miss a shoulder limit.
    elbow = 0.0 if cosine >= 1.0 - 1e-14 else math.acos(max(-1.0, min(1.0, cosine)))
    shoulder = math.atan2(x, down) - math.atan2(FOREARM_M * math.sin(elbow), UPPER_ARM_M + FOREARM_M * math.cos(elbow))
    if not -.1 - 1e-10 <= shoulder <= .65 + 1e-10 or not 0 <= elbow <= .9 + 1e-10:
        raise ValueError('target has no solution within this fixture\'s joint limits')
    shoulder = max(-.1, min(.65, shoulder))
    elbow = min(.9, elbow)
    try:
        import mujoco
    except ImportError:
        raise RuntimeError('MuJoCo is unavailable; install the optional simulation dependency. No mock was run.') from None
    scene = (Path(__file__).with_name('data') / 'articulated_scene.xml').read_text(encoding='utf-8')
    model = mujoco.MjModel.from_xml_string(scene)
    data = mujoco.MjData(model)
    for name, value in (('left_shoulder', shoulder), ('left_elbow', elbow)):
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        actuator = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if joint < 0 or actuator < 0:
            raise RuntimeError('packaged fixture is missing a required arm joint or actuator')
        if (not float(model.jnt_range[joint, 0]) <= value <= float(model.jnt_range[joint, 1])
            or not float(model.actuator_ctrlrange[actuator, 0]) <= value <= float(model.actuator_ctrlrange[actuator, 1])):
            raise RuntimeError('planned target disagrees with packaged joint/actuator limits')
        data.qpos[model.jnt_qposadr[joint]] = value
    hand = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, 'left_hand_geom')
    if hand < 0:
        raise RuntimeError('packaged fixture is missing the left hand')
    mujoco.mj_forward(model, data)
    predicted = tuple(float(value) for value in data.geom_xpos[hand])
    residual = math.dist(target, predicted)
    if not math.isfinite(residual) or residual > 1e-9:
        raise RuntimeError('analytic arm geometry disagrees with packaged forward kinematics')
    return HandTargetPlan(target, shoulder, elbow, predicted, residual,
                          hashlib.sha256(scene.encode('utf-8')).hexdigest(), mujoco.__version__)


def run_hand_target(target_m: tuple[float, float, float], *, scenario: str = 'clear_path',
                    steps: int = 1000, confirm_simulation: bool = False) -> ReachReport:
    plan = plan_hand_target(target_m)
    physics = run_articulation_scenario(scenario, steps=steps, confirm_simulation=confirm_simulation,
                                       left_arm_target_rad=(plan.shoulder_rad, plan.elbow_rad))
    if physics.scene_sha256 != plan.scene_sha256:
        raise RuntimeError('packaged scene changed between planning and simulation; discard this run')
    error = math.dist(plan.target_m, physics.final_hand_position_m)
    within = error <= ENDPOINT_TOLERANCE_M
    settled = max(abs(value) for value in physics.final_joint_velocities_rad_s.values()) <= SETTLED_RATE_RAD_S
    reached = (physics.simulation_confirmed and physics.stop_reason is None
               and physics.terminal_reason == 'step_budget_reached'
               and physics.obstacle_contacts == 0 and physics.self_contacts == 0 and within and settled)
    return ReachReport(plan, physics, error, within, settled, reached)
