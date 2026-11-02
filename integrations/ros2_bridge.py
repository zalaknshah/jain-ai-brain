"""Optional ROS 2 boundary.

This module intentionally has no ROS dependency. A ROS 2 package can call
``SafeActionBridge.publish`` after converting an approved JACE action into its
own message type. Physical movement must remain confirmation-gated.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class SafeActionBridge:
    publisher: Callable[[dict[str, Any]], None]

    def publish(self, action: dict[str, Any], confirmed: bool = False) -> bool:
        if not confirmed:
            return False
        if action.get("action") != "propose_safe_navigation":
            return False
        params = action.get("parameters", {})
        if params.get("avoid_contact") is not True or params.get("speed") != "slow":
            return False
        self.publisher(action)
        return True
