from __future__ import annotations

from dataclasses import dataclass, asdict
import math
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
    # Missing, malformed or non-finite sensor values are unknown, never clear.
    def unknown() -> SimulationDecision:
        return SimulationDecision("HALT_AND_REROUTE", "Safety: sensor data is missing or invalid; remain stopped.", 0.0, 0.5, True, False)

    if not isinstance(observation, dict) or "distance_m" not in observation:
        return unknown()
    raw_distance = observation["distance_m"]
    raw_uncertainty = observation.get("uncertainty", 0.0)
    if (isinstance(raw_distance, bool) or not isinstance(raw_distance, (int, float))
            or isinstance(raw_uncertainty, bool) or not isinstance(raw_uncertainty, (int, float))):
        return unknown()
    distance = float(raw_distance)
    uncertainty = float(raw_uncertainty)
    if not math.isfinite(distance) or distance < 0 or not math.isfinite(uncertainty) or not 0 <= uncertainty <= 1:
        return unknown()
    living = observation.get("living_entity", False)
    fragile = observation.get("fragile_object", False)
    if not isinstance(living, bool) or not isinstance(fragile, bool):
        return unknown()
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
