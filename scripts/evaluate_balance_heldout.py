"""Replay independent frozen-controller cases, not a walking qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
CONTROLLER_SHA256 = '2d0d9970b33c074ed1569a2c96bb0b8ff1ce1e0e5887bf80198b6b56ecc59726'
CASE_SHA256 = 'a68d54c6331ee761ebf7bbb722200c73660f399562de86ea770f85912cef6646'
EXPECTED_FAILURES = {'review_strong_front_right': 'unexpected_contact_detected',
                     'review_strong_backward': 'posture_guard_triggered'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-simulation', action='store_true')
    parser.add_argument('--case', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.confirm_simulation:
        parser.error('--confirm-simulation is required; no physics was run')
    if os.name != 'posix' or sys.platform != 'linux':
        parser.error('Linux/POSIX resource limits required; no unrestricted fallback')
    case_bytes = (ROOT / 'evals/balance/heldout_cases.json').read_bytes()
    controller_bytes = (ROOT / 'src/jace/freebase_balance_controller.py').read_bytes()
    if hashlib.sha256(case_bytes).hexdigest() != CASE_SHA256 or hashlib.sha256(controller_bytes).hexdigest() != CONTROLLER_SHA256:
        parser.error('frozen controller or preregistered cases changed; no physics was run')
    cases = json.loads(case_bytes)
    if args.case:
        if args.case not in cases:
            parser.error('unknown fixed case')
        from jace.freebase_worker import _apply_resource_limits, _run
        _apply_resource_limits()
        import jace.freebase_balance as balance
        # Evaluation-only substitution of fixed, independently selected forces.
        # No arbitrary model, code, user force parameters or gain inputs accepted.
        balance.DISTURBANCES = {args.case: cases[args.case]}
        balance.SCENARIOS = (args.case,)
        report = _run(args.case, 2000, False, confirm_simulation=True, controller='posture_feedback')
        print(json.dumps(report, allow_nan=False))
        return 0
    results, failures = [], []
    env = {'PATH': os.defpath, 'PYTHONPATH': str(ROOT / 'src'), 'PYTHONNOUSERSITE': '1',
           'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    for name in cases:
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--case', name,
                                     '--confirm-simulation'], env=env, capture_output=True, text=True,
                                    timeout=30, check=False)
            if result.returncode:
                raise RuntimeError(f'worker exit {result.returncode}: {result.stderr[:500]}')
            report = json.loads(result.stdout)
            if report.get('schema') != 'jace.freebase.balance.v1':
                raise ValueError('unexpected report schema')
            report['resource_limits']['outer_wall_seconds'] = 30
            results.append(report)
            expected = EXPECTED_FAILURES.get(name, 'step_budget_reached')
            if report['terminal_reason'] != expected:
                failures.append(f'{name}: unexpected terminal reason')
            if report['finite_horizon_posture_accepted'] != (name not in EXPECTED_FAILURES):
                failures.append(f'{name}: wrong finite-horizon classification')
            if any(report[key] for key in ('standing_verified', 'balance_qualified', 'walking_verified',
                    'locomotion_controller', 'hardware_enabled', 'pretrained_policy_loaded',
                    'external_support_enabled', 'root_state_written_during_episode')):
                failures.append(f'{name}: unsupported capability claim')
        except (subprocess.TimeoutExpired, RuntimeError, ValueError, KeyError) as error:
            failures.append(f'{name}: worker/report error, not success: {error}')
    print(json.dumps({'regression_assertions_passed': not failures, 'failures': failures,
        'scope': 'Six accepted eight-second posture cases and two guard failures; not balance or gait qualification',
        'selection': 'Independently selected after controller freeze; future reuse is regression, not new heldout evidence',
        'controller_sha256': CONTROLLER_SHA256, 'case_definition_sha256': CASE_SHA256,
        'results': results}, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
