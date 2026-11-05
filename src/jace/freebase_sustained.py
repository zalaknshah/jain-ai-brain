"""Isolated resource-bounded six-step experiment. No hardware or learned policy."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .freebase_sustained_resources import apply_observed_resource_verdict

from .freebase_gait import (ControllerFeasibilityError, validate_gait_runtime,
                            validate_gait_backend_versions)

CONTROLLER_ID = 'g1-contact-six-step-prototype-v1'
MAX_STEPS = 5000
WALL_TIMEOUT_S = 30
DISTURBANCES = {'neutral_posture': None, 'initial_tilt': None, 'sensor_dropout': None,
               'strong_forward_third_swing': (1800, 1850, (300., 0., 0.))}
SCENARIOS = tuple(DISTURBANCES)


def run_sustained_probe(scenario: str = 'neutral_posture', *, steps: int = MAX_STEPS,
                        confirm_simulation: bool = False, include_trace: bool = False) -> dict:
    return _run_capped_worker(scenario, steps=steps, confirm_simulation=confirm_simulation,
                             include_trace=include_trace)


def _run_capped_worker(scenario: str, *, steps: int, confirm_simulation: bool,
                       include_trace: bool) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError('unknown free-base diagnostic scenario')
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f'steps must be an integer between 1 and {MAX_STEPS}')
    if type(confirm_simulation) is not bool or type(include_trace) is not bool:
        raise ValueError('confirmation and trace choices must be boolean')
    if not confirm_simulation:
        raise ValueError('explicit simulation confirmation is required; no diagnostic physics was run')
    if os.name != 'posix' or sys.platform != 'linux':
        raise RuntimeError('this diagnostic requires Linux/POSIX process resource limits; no unrestricted fallback is run')
    validate_gait_runtime()
    # A clean subprocess, not a security sandbox for arbitrary executable models.
    # Only our packaged, hash-checked XML is accepted. Never load TorchScript here.
    env = {'PATH': os.defpath, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
           'PYTHONNOUSERSITE': '1', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    module = 'jace.freebase_sustained_worker'
    command = [sys.executable, '-m', module, scenario, str(steps),
               'trace' if include_trace else 'summary', '--confirmed-simulation']
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=WALL_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('free-base diagnostic exceeded its wall-time cap; process stopped, outcome is not a success') from None
    if result.returncode != 0:
        detail = result.stderr.strip()[:500]
        raise RuntimeError(f'free-base diagnostic failed (exit {result.returncode}); no success claimed: {detail}')
    try:
        report = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('invalid diagnostic report; no success claimed') from None
    if not isinstance(report, dict) or report.get('schema') != 'jace.freebase.sustained_probe.v1':
        raise RuntimeError('unexpected diagnostic report; no success claimed')
    if isinstance(report.get('resource_limits'), dict):
        report['resource_limits']['outer_wall_seconds'] = WALL_TIMEOUT_S
    report['outer_elapsed_wall_seconds'] = time.monotonic() - started
    return apply_observed_resource_verdict(report, include_outer_wall=True)
