"""Exercise actual optional MuJoCo fixtures; never substitute a mock backend."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from jace.physics import SCENARIOS, run_physics_scenario  # noqa: E402


def main() -> int:
    results = []
    failures = []
    try:
        for scenario in SCENARIOS:
            report = run_physics_scenario(scenario, steps=1000, confirm_simulation=True)
            results.append(report.to_dict())
            if report.steps != 1000 or report.obstacle_contacts or report.hardware_enabled or report.minimum_clearance_m < 0.5:
                failures.append(f'{scenario}: failed fixture bounds/contact assertions')
            if scenario == 'clear_path' and report.final_position_m <= 1.0:
                failures.append(f'{scenario}: expected actual movement')
            if scenario != 'clear_path' and abs(report.final_velocity_m_s) >= 1e-6:
                failures.append(f'{scenario}: did not settle to a stop')
            if scenario in {'living_obstacle', 'uncertain_sensor'} and report.travelled_distance_m != 0:
                failures.append(f'{scenario}: unexpected movement')
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'fixture_assertions_passed': not failures, 'failures': failures, 'results': results}, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
