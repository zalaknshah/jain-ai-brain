from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SimulationDecision:
    action: str
    reason: str
    velocity: float
    clearance_distance: float
    requires_confirmation: bool = True
    executable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_motion(observation: dict[str, Any]) -> SimulationDecision:
    """Turn simulator perception into a conservative high-level decision.

    This deliberately does not emit joint torques. A ROS 2 controller must
    perform collision checking, limits, emergency-stop handling, and its own
    confirmation policy before executing anything.
    """
    distance = max(0.0, float(observation.get("distance_m", 99.0)))
    living = bool(observation.get("living_entity", False))
    fragile = bool(observation.get("fragile_object", False))
    uncertainty = float(observation.get("uncertainty", 0.0))
    if living or fragile or distance < 0.5 or uncertainty > 0.5:
        reason = "Ahimsa: pause and increase distance before contact." if living else "Safety: pause until the obstacle and clearance are resolved."
        return SimulationDecision("HALT_AND_REROUTE", reason, 0.0, max(0.5, distance), True, False)
    if distance < 1.5:
        return SimulationDecision("SLOW_AND_OBSERVE", "Maintain a generous clearance and reassess before moving closer.", 0.1, 1.5, True, False)
    return SimulationDecision("PROCEED_SLOWLY", "No immediate obstacle risk detected; use the least forceful movement.", 0.25, 1.0, True, False)


def run_scenarios() -> list[dict[str, Any]]:
    scenarios = {
        "small_living_entity": {"distance_m": 0.2, "living_entity": True},
        "fragile_object": {"distance_m": 0.8, "fragile_object": True},
        "clear_path": {"distance_m": 3.0},
        "uncertain_sensor": {"distance_m": 2.0, "uncertainty": 0.8},
    }
    return [{"name": name, "observation": observation, "decision": decide_motion(observation).to_dict()} for name, observation in scenarios.items()]
