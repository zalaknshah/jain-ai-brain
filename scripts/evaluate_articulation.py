"""Actual fixed-base MuJoCo articulation checks, including expected contact failure."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jace.articulated import ARTICULATION_SCENARIOS, run_articulation_scenario  # noqa: E402


def main() -> int:
    results=[]
    failures=[]
    try:
        for scenario in ARTICULATION_SCENARIOS:
            report=run_articulation_scenario(scenario,steps=1000,confirm_simulation=True)
            results.append(report.to_dict())
            if scenario=='unavoidable_overlap':
                if report.terminal_reason!='contact_detected' or report.obstacle_contacts<1 or report.minimum_clearance_m>=0:
                    failures.append('unavoidable_overlap: contact was not honestly detected')
                continue
            if (report.steps!=1000 or report.terminal_reason!='step_budget_reached'
                or report.obstacle_contacts or report.self_contacts or report.minimum_clearance_m<.5
                or report.maximum_actuator_torque_nm>15 or report.maximum_measured_joint_rate_rad_s>.6):
                failures.append(f'{scenario}: modeled contact or fixture-bound failure')
            if any(abs(value)>1e-6 for value in report.final_joint_velocities_rad_s.values()):
                failures.append(f'{scenario}: did not settle within the test horizon')
            if scenario=='clear_path' and report.final_joints_rad['left_shoulder']<.5:
                failures.append('clear_path: expected articulated movement')
    except RuntimeError as error:
        print(str(error),file=sys.stderr)
        return 2
    print(json.dumps({'fixture_assertions_passed':not failures,'failures':failures,
                      'scope':'Six limited articulation cases plus one expected-contact adversarial case; not humanoid qualification',
                      'results':results},indent=2))
    return 1 if failures else 0


if __name__=='__main__':
    raise SystemExit(main())
