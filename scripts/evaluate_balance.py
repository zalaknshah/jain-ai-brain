"""Finite-horizon posture feedback evidence; expected failures remain failures.

Running this evaluation explicitly consents to bounded local simulation. It runs
no hardware, network services, pretrained code, external models or paid compute.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from jace.freebase import run_freebase_diagnostic
from jace.freebase_balance import SCENARIOS, run_freebase_balance

EXPECTED = {
    'neutral_posture': 'step_budget_reached',
    'forward_push': 'posture_guard_triggered',
    'lateral_push': 'unexpected_contact_detected',
    'backward_push': 'step_budget_reached',
    'diagonal_push': 'step_budget_reached',
    'reverse_lateral_push': 'step_budget_reached',
    'initial_tilt': 'posture_guard_triggered',
    'sensor_dropout': 'sensor_guard_triggered',
}


def main() -> int:
    failures, results = [], []
    try:
        baseline = run_freebase_diagnostic(confirm_simulation=True)
        for scenario in SCENARIOS:
            report = run_freebase_balance(scenario, confirm_simulation=True)
            results.append(report)
            if report['terminal_reason'] != EXPECTED[scenario]:
                failures.append(f'{scenario}: unexpected terminal reason')
            expected_acceptance = EXPECTED[scenario] == 'step_budget_reached'
            if report['finite_horizon_posture_accepted'] != expected_acceptance:
                failures.append(f'{scenario}: wrong finite-horizon outcome')
            if any(report[key] for key in ('standing_verified', 'balance_qualified', 'walking_verified',
                    'locomotion_controller', 'pretrained_policy_loaded', 'hardware_enabled',
                    'external_support_enabled', 'root_state_written_during_episode')):
                failures.append(f'{scenario}: unsupported capability')
            if expected_acceptance and (report['maximum_tilt_rad'] > .1
                    or report['minimum_pelvis_height_m'] < .75 or report['settled_tail_s'] < 1):
                failures.append(f'{scenario}: accepted fixture bound regressed')
        if baseline['terminal_reason'] != 'posture_guard_triggered' or not .9 < baseline['elapsed_simulation_s'] < 1.2:
            failures.append('original neutral-servo failure did not reproduce')
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'regression_assertions_passed': not failures, 'failures': failures,
          'scope': 'Four accepted eight-second posture cases and four reported guard failures; no walking qualification',
          'controller_selected_on': 'neutral and development perturbations; these cases are not held out',
          'baseline': baseline, 'results': results}, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
