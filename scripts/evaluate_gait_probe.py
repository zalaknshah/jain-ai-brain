"""Reproduce bounded two-step and explicit failure outcomes, not walking qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.freebase_gait import SCENARIOS, run_gait_probe

FROZEN_CONTROLLER_SHA256 = '7f2ed4f7db866e66514645dd2920c512ee6c0e1b9ad5fba41fba9236e0defdce'
EXPECTED_FAILURES = {'initial_tilt': 'posture_guard_triggered',
                     'sensor_dropout': 'sensor_guard_triggered',
                     'strong_forward_first_swing': 'posture_guard_triggered'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-simulation', action='store_true')
    args = parser.parse_args()
    if not args.confirm_simulation:
        parser.error('--confirm-simulation is required; no physics was run')
    actual_hash = hashlib.sha256((ROOT / 'src/jace/freebase_gait_controller.py').read_bytes()).hexdigest()
    if actual_hash != FROZEN_CONTROLLER_SHA256:
        parser.error('frozen experimental controller changed; no physics was run')
    results, failures = [], []
    for scenario in SCENARIOS:
        try:
            report = run_gait_probe(scenario, confirm_simulation=True)
            results.append(report)
            expected = EXPECTED_FAILURES.get(scenario, 'step_budget_reached')
            if report['terminal_reason'] != expected:
                failures.append(f'{scenario}: unexpected terminal reason')
            if report['two_step_probe_accepted'] != (scenario not in EXPECTED_FAILURES):
                failures.append(f'{scenario}: incorrect bounded two-step classification')
            if any(report[key] for key in ('walking_verified', 'balance_qualified', 'standing_verified',
                    'hardware_enabled', 'external_support_enabled', 'root_state_written_during_episode',
                    'pretrained_policy_loaded')):
                failures.append(f'{scenario}: unsupported qualification claim')
            if report['maximum_controller_iterations'] > 64 or report['maximum_controller_inequality_residual'] > 1e-4:
                failures.append(f'{scenario}: controller feasibility bound failed')
            if any(report['numerical_warning_counts'].values()):
                failures.append(f'{scenario}: unexpected numerical warning')
        except (RuntimeError, ValueError) as error:
            failures.append(f'{scenario}: process/controller error, not success: {error}')
    print(json.dumps({'regression_assertions_passed': not failures, 'failures': failures,
          'scope': 'Eight accepted two-step horizons and three explicit guard failures, not general walking qualification',
          'controller_sha256': FROZEN_CONTROLLER_SHA256, 'results': results}, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
