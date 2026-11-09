"""Reproduce the frozen six-step probe and explicit failures, not walking qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.freebase_sustained import SCENARIOS, run_sustained_probe

EXPECTED = {'neutral_posture': 'step_budget_reached',
            'initial_tilt': 'posture_guard_triggered', 'sensor_dropout': 'sensor_guard_triggered',
            'strong_forward_third_swing': 'controller_feasibility_guard_triggered'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-simulation', action='store_true')
    args = parser.parse_args()
    if not args.confirm_simulation:
        parser.error('--confirm-simulation is required; no physics was run')
    manifest = json.loads((ROOT / 'evals/sustained_gait/lifetime_accounting_freeze.json').read_text())
    for name, expected in manifest['implementation_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            parser.error(f'frozen source changed: {name}; no physics was run')
    results, failures = [], []
    for scenario in SCENARIOS:
        try:
            report = run_sustained_probe(scenario, confirm_simulation=True)
            results.append(report)
            if report['terminal_reason'] != EXPECTED[scenario]:
                failures.append(f'{scenario}: unexpected terminal reason')
            if report['sustained_probe_accepted'] != (scenario == 'neutral_posture'):
                failures.append(f'{scenario}: overall acceptance differs from the fixed regression expectation; '
                                f'physical={report["physical_six_step_criteria_met"]}, '
                                f'observed_budget={report["observed_resource_budget_satisfied"]}, '
                                f'violations={report["resource_budget_violations"]}')
            if any(report[key] for key in ('walking_verified', 'balance_qualified', 'standing_verified',
                    'hardware_enabled', 'external_support_enabled', 'root_state_written_during_episode',
                    'pretrained_policy_loaded')):
                failures.append(f'{scenario}: unsupported qualification claim')
            if report['maximum_controller_iterations'] > 64 or report['maximum_controller_inequality_residual'] > 1e-4:
                failures.append(f'{scenario}: executed controller feasibility bound failed')
            if any(report['numerical_warning_counts'].values()):
                failures.append(f'{scenario}: unexpected numerical warning')
        except (RuntimeError, ValueError) as error:
            failures.append(f'{scenario}: process/controller error, not success: {error}')
    print(json.dumps({'regression_assertions_passed': not failures, 'failures': failures,
                     'scope': 'Physical and observed-resource regression; nominal acceptance and three guard failures expected, not general walking or resource reliability qualification',
                     'candidate_id': manifest['candidate_id'], 'results': results}, indent=2, allow_nan=False))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
