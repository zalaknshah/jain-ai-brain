"""Require honest instability/fall reporting, not successful standing or walking."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from jace.freebase import SCENARIOS, run_freebase_diagnostic


def main() -> int:
    results, failures = [], []
    expected = {'neutral_posture': 'posture_guard_triggered', 'forward_push': 'posture_guard_triggered',
                'lateral_push': 'unexpected_contact_detected', 'initial_tilt': 'posture_guard_triggered',
                'sensor_dropout': 'sensor_guard_triggered'}
    try:
        for scenario in SCENARIOS:
            report = run_freebase_diagnostic(scenario, confirm_simulation=True)
            results.append(report)
            if report['terminal_reason'] != expected[scenario] or report['no_guard_triggered_within_horizon']:
                failures.append(f'{scenario}: expected diagnostic failure was not reported')
            if any(report[key] for key in ('standing_verified', 'locomotion_controller', 'pretrained_policy_loaded', 'hardware_enabled')):
                failures.append(f'{scenario}: unsupported success/capability claim')
        if results[0]['maximum_tilt_rad'] <= .5:
            failures.append('neutral instability was not reproduced')
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'diagnostic_assertions_passed': not failures, 'failures': failures,
                      'scope': 'Five expected diagnostic guard outcomes, not five successful humanoid tasks',
                      'results': results}, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
