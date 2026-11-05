"""Measured finite-horizon two-step observations, separate from run acceptance."""
from __future__ import annotations


def summarize_two_step_probe(trace, events, initial_feet, final_feet, initial_root,
                             final_root, final_clearance, final_time):
    displacement = [[float(end[k] - start[k]) for k in range(3)]
                    for start, end in zip(initial_feet, final_feet)]
    intervals = []
    for side in (0, 1):
        start = None
        maximum_clearance = 0.
        for entry in trace:
            airborne = entry['contacts'][side] == 0
            if airborne and start is None:
                start = entry['t']
                maximum_clearance = 0.
            if airborne:
                maximum_clearance = max(maximum_clearance, entry['foot_clearance_m'][side])
            elif start is not None:
                intervals.append({'foot': ('left', 'right')[side], 'start_s': start,
                                  'end_s': entry['t'], 'landed': True,
                                  'maximum_capsule_clearance_m': maximum_clearance})
                start = None
        if start is not None:
            intervals.append({'foot': ('left', 'right')[side], 'start_s': start,
                              'end_s': final_time, 'landed': False,
                              'maximum_capsule_clearance_m': maximum_clearance})
    intervals.sort(key=lambda entry: entry['start_s'])
    support_runs = []
    active, began = None, None
    for entry in trace:
        support = None
        for side in (0, 1):
            if (entry['contacts'][side] > 0 and entry['normal_forces_n'][side] > 50
                    and entry['contacts'][1-side] == 0):
                support = ('left', 'right')[side]
        if support != active:
            if active is not None:
                support_runs.append({'support_foot': active, 'start_s': began, 'end_s': entry['t']})
            active, began = support, entry['t']
    if active is not None:
        support_runs.append({'support_foot': active, 'start_s': began, 'end_s': final_time})
    substantial = [run for run in support_runs if run['end_s'] - run['start_s'] >= .1 - 1e-8]
    ordered_support = any(first['support_foot'] == 'right' and second['support_foot'] == 'left'
                          and second['start_s'] >= first['end_s']
                          for first in substantial for second in substantial)
    cleared_and_landed = [any(run['foot'] == side and run['landed']
                             and run['maximum_capsule_clearance_m'] >= .01
                             for run in intervals) for side in ('left', 'right')]
    final_second = [entry for entry in trace if entry['t'] >= final_time - 1. - 1e-8]
    final_double_support = len(final_second) >= 249 and all(
        all(entry['contacts'][side] > 0 and entry['normal_forces_n'][side] > 20 for side in (0, 1))
        for entry in final_second)
    pelvis_advance = float(final_root[0] - initial_root[0])
    phase_order = [entry['to'] for entry in events]
    expected_phases = ['shift_right', 'swing_left', 'shift_left', 'swing_right', 'recover']
    sequence = (phase_order == expected_phases and ordered_support and all(cleared_and_landed)
                and displacement[0][0] >= .03 and displacement[1][0] >= .06
                and pelvis_advance >= .025 and abs(final_root[1] - initial_root[1]) <= .03)
    return {
        'phase_transitions': events, 'final_phase': trace[-1]['phase'] if trace else 'not_started',
        'initial_foot_body_positions_m': initial_feet, 'final_foot_body_positions_m': final_feet,
        'foot_body_displacements_m': displacement, 'net_pelvis_advance_m': pelvis_advance,
        'maximum_foot_capsule_clearance_m': [max((x['foot_clearance_m'][i] for x in trace), default=0.)
                                             for i in (0, 1)],
        'final_foot_capsule_clearance_m': final_clearance,
        'airborne_intervals': intervals, 'loaded_single_support_intervals': support_runs,
        'ordered_alternating_support_observed': ordered_support,
        'both_feet_cleared_and_landed': all(cleared_and_landed),
        'last_second_double_support_observed': final_double_support,
        'two_step_sequence_observed': bool(sequence),
        'out_of_planned_swing_airborne_observations': {
            side: sum(entry['contacts'][i] == 0 and entry['phase'] != 'swing_' + side for entry in trace)
            for i, side in enumerate(('left', 'right'))},
        'maximum_controller_inequality_residual': max((max(0., x.get('constraint_residual', 0.)) for x in trace), default=0.),
        'maximum_controller_iterations': max((x.get('qp_iterations', 0) for x in trace), default=0),
        'contact_wrenches_are_prediction_only': True,
        'standing_verified': False, 'walking_verified': False, 'balance_qualified': False,
    }
