"""Deterministic actual-physics reach checks, not a general manipulation benchmark."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.reaching import plan_hand_target, run_hand_target  # noqa: E402

TARGETS = (
    (.12756712895647063, .22, .8883009199660632),
    (.2753504088124071, .22, .9627989630659425),
    (.3793621955923912, .22, 1.07070369520417),
    (.40627814031000703, .22, 1.1387803354834483),
)


def main() -> int:
    results, failures, rejections = [], [], []
    try:
        for target in TARGETS:
            report = run_hand_target(target, confirm_simulation=True)
            results.append({'expected': 'reach', **report.to_dict()})
            if (not report.target_reached or report.endpoint_error_m > .02
                or report.physics.maximum_actuator_torque_nm > 15
                or report.physics.maximum_measured_joint_rate_rad_s > .6):
                failures.append(f'{target}: bounded reach expectations not met')
        for scenario, confirmed, steps in (
            ('clear_path', False, 1000), ('clear_path', True, 10),
            ('static_obstacle', True, 1000), ('living_obstacle', True, 1000),
            ('obstacle_intrusion', True, 1000), ('sensor_dropout', True, 1000),
            ('uncertain_sensor', True, 1000), ('unavoidable_overlap', True, 1000),
        ):
            report = run_hand_target(TARGETS[2], scenario=scenario, steps=steps, confirm_simulation=confirmed)
            results.append({'expected': 'not_reached', **report.to_dict()})
            if report.target_reached:
                failures.append(f'{scenario}: unexpectedly claimed reach')
            if scenario == 'unavoidable_overlap':
                if report.physics.terminal_reason != 'contact_detected' or report.physics.obstacle_contacts < 1:
                    failures.append('unavoidable_overlap: expected collision not detected')
            elif report.physics.obstacle_contacts or report.physics.self_contacts:
                failures.append(f'{scenario}: unexpected modeled contact')
        for target in ((2, .22, 1), (.3, .3, 1), (0, .22, 1.1)):
            try:
                plan_hand_target(target)
            except ValueError as error:
                rejections.append({'target_m': target, 'reason': str(error)})
            else:
                failures.append(f'{target}: impossible target accepted')
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({'fixture_assertions_passed': not failures, 'failures': failures,
                      'scope': 'Four limited reaches, eight non-success cases including expected contact, three target rejections; no hardware qualification',
                      'results': results, 'rejections': rejections}, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
