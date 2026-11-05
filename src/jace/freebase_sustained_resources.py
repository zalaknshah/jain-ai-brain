"""Conservative classification of observed resource counters, not lifetime proof."""
from __future__ import annotations
import math

CPU_BUDGET_SECONDS = 15
WALL_BUDGET_SECONDS = 30
ADDRESS_SPACE_LIMIT_BYTES = 1024**3


def apply_observed_resource_verdict(report: dict, *, include_outer_wall: bool) -> dict:
    """Keep physical observations; reject known overages or absent/invalid evidence.

    Worker CPU is cumulative process CPU sampled before output/exit, not merely
    simulation CPU. It is a lower bound on final process CPU. An in-budget sample
    cannot establish whole-lifetime compliance or general resource reliability.
    """
    physical = (report.get('steps') == 5000
                and report.get('terminal_reason') == 'step_budget_reached'
                and all(report.get(key) is True for key in (
                    'finite_horizon_posture_accepted', 'six_step_sequence_observed',
                    'last_second_double_support_observed')))
    failures = []
    limits = report.get('resource_limits')
    if not isinstance(limits, dict):
        limits = {}
    expected = {'address_space_bytes': ADDRESS_SPACE_LIMIT_BYTES,
                'cpu_seconds': CPU_BUDGET_SECONDS}
    if include_outer_wall:
        expected['outer_wall_seconds'] = WALL_BUDGET_SECONDS
    for name, value in expected.items():
        if type(limits.get(name)) is not int or limits[name] != value:
            failures.append('configured_' + name + '_missing_or_unexpected')
    counters = {'worker_cpu_seconds_used': CPU_BUDGET_SECONDS,
                'worker_elapsed_wall_seconds': WALL_BUDGET_SECONDS}
    if include_outer_wall:
        counters['outer_elapsed_wall_seconds'] = WALL_BUDGET_SECONDS
    for name, budget in counters.items():
        value = report.get(name)
        if (type(value) not in (int, float) or value < 0
                or (type(value) is float and not math.isfinite(value))):
            failures.append(name + '_missing_or_invalid')
        elif value > budget:
            failures.append(name + '_exceeded')
    report.update(
        physical_six_step_criteria_met=bool(physical),
        observed_resource_budget_satisfied=not failures,
        resource_budget_violations=failures,
        resource_verdict_stage='launcher_return' if include_outer_wall else 'worker_report',
        resource_accounting_scope={
            'worker_cpu': 'Cumulative worker-process CPU through the reporting sample, including startup/imports; excludes later verdict, JSON/output and process exit.',
            'worker_wall': 'Monotonic elapsed time from _run entry through the reporting sample; excludes prior startup and later verdict/output/exit.',
            'outer_wall': ('Launcher elapsed time through subprocess completion and response parsing, before the final verdict and caller work.'
                           if include_outer_wall else 'Not measured here; launcher must assess its own elapsed time.'),
            'full_worker_lifetime_cpu_measured': False,
            'resource_reliability_qualified': False},
        sustained_probe_accepted=bool(physical and not failures))
    return report
