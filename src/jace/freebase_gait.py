"""Experimental bounded two-step sequence, never general walking qualification."""
from __future__ import annotations
from importlib import metadata
import sys
from .freebase import _run_capped_worker, MAX_STEPS

CONTROLLER_ID = 'g1-contact-two-step-prototype-v1'
GAIT_MIN_PYTHON = (3, 12)
GAIT_DEPENDENCIES = {'mujoco': '3.17.0', 'numpy': '2.5.4'}
DISTURBANCES = {'neutral_posture': None, 'initial_tilt': None, 'sensor_dropout': None,
               'forward_push': (100, 125, (100., 0., 0.)),
               'lateral_push': (100, 125, (0., 100., 0.)),
               # Independently chosen after freezing the controller, not used to tune it.
               'small_forward_transfer': (225, 250, (12., 0., 0.)),
               'small_backward_first_swing': (575, 600, (-12., 0., 0.)),
               'small_lateral_first_swing': (625, 650, (0., 12., 0.)),
               # Historical case label; this pulse actually occurs in right swing.
               'medium_reverse_lateral_transfer': (1150, 1175, (0., -25., 0.)),
               'medium_diagonal_second_swing': (1325, 1350, (25., 25., 0.)),
               'strong_forward_first_swing': (575, 625, (300., 0., 0.))}
SCENARIOS = tuple(DISTURBANCES)


class ControllerFeasibilityError(RuntimeError):
    """A finite bounded controller solution was not found; stop before stepping."""


def validate_gait_runtime() -> None:
    """Check the qualified optional stack without importing a physics backend."""
    if sys.version_info[:2] < GAIT_MIN_PYTHON:
        current = '.'.join(str(part) for part in sys.version_info[:2])
        raise RuntimeError(f'experimental gait requires Python 3.12+; found Python {current}. '
                           'Use a Python 3.12+ environment with the gait extra; no gait physics was run')
    mismatches = []
    for name, expected in GAIT_DEPENDENCIES.items():
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = 'not installed'
        if actual != expected:
            mismatches.append(f'{name}=={expected} required, found {actual}')
    if mismatches:
        raise RuntimeError('experimental gait dependency mismatch: ' + '; '.join(mismatches)
                           + '. Use the gait extra in Python 3.12+; no gait physics was run')


def validate_gait_backend_versions(mujoco_version: str, numpy_version: str) -> None:
    """Recheck loaded versions before creating the simulation model."""
    loaded = {'mujoco': mujoco_version, 'numpy': numpy_version}
    mismatches = [f'{name}=={expected} required, loaded {loaded[name]}'
                  for name, expected in GAIT_DEPENDENCIES.items() if loaded[name] != expected]
    if mismatches:
        raise RuntimeError('experimental gait backend mismatch: ' + '; '.join(mismatches)
                           + '; no gait model or physics was started')


def run_gait_probe(scenario: str = 'neutral_posture', *, steps: int = MAX_STEPS,
                   confirm_simulation: bool = False, include_trace: bool = False) -> dict:
    return _run_capped_worker(scenario, steps=steps, confirm_simulation=confirm_simulation,
                             include_trace=include_trace, mode='gait_probe')
