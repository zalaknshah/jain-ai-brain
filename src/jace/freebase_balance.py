"""Finite-horizon posture feedback experiment, strictly simulation only.

No arbitrary gains, models, weights, hardware or network endpoints are accepted.
This module has no optional numerical dependency until the capped worker starts.
"""
from __future__ import annotations

from .freebase import _run_capped_worker, MAX_STEPS

CONTROLLER_ID = 'g1-posture-feedback-v1'
# Development cases, not heldout validation. Intervals are step indices at 0.004 s
# per step; forces are world-frame N. The original 100 N diagnostic cases remain
# failure probes. Gains were frozen before independent review selected other cases.
DISTURBANCES = {
    'neutral_posture': None,
    'forward_push': (100, 125, (100.0, 0.0, 0.0)),
    'lateral_push': (100, 125, (0.0, 100.0, 0.0)),
    'backward_push': (200, 225, (-60.0, 0.0, 0.0)),
    'diagonal_push': (200, 225, (45.0, 45.0, 0.0)),
    'reverse_lateral_push': (300, 325, (0.0, -60.0, 0.0)),
    'initial_tilt': None,
    'sensor_dropout': None,
}
SCENARIOS = tuple(DISTURBANCES)


def run_freebase_balance(scenario: str = 'neutral_posture', *, steps: int = MAX_STEPS,
                         confirm_simulation: bool = False, include_trace: bool = False) -> dict:
    """Run a bounded numerical experiment, not a balance or walking certificate."""
    return _run_capped_worker(scenario, steps=steps, confirm_simulation=confirm_simulation,
                             include_trace=include_trace, mode='balance')
