"""Measured six-step observations; phase commands alone never imply acceptance."""
from __future__ import annotations
from .freebase_gait_metrics import summarize_two_step_probe

SIDES = ('left', 'right')
EXPECTED_PHASES = ['shift_right', 'swing_left', 'shift_left', 'swing_right'] * 3 + ['recover']


def _longest_run(samples, predicate):
    """Conservative elapsed time between observed endpoints, not sample count * dt."""
    began = None
    longest = 0.
    for entry in samples:
        if predicate(entry):
            if began is None:
                began = entry['t']
            longest = max(longest, entry['t'] - began)
        else:
            began = None
    return longest


def summarize_sustained_probe(trace, events, initial_feet, final_feet, initial_root,
                               final_root, final_clearance, final_time):
    report = summarize_two_step_probe(trace, events, initial_feet, final_feet,
                                     initial_root, final_root, final_clearance, final_time)
    # Keep generic measurements, but do not reuse two-step acceptance or support order.
    report.pop('two_step_sequence_observed')
    report.pop('ordered_alternating_support_observed')
    steps = []
    for event_index, event in enumerate(events):
        if event['to'] not in ('swing_left', 'swing_right'):
            continue
        side = SIDES.index(event['to'][6:])
        next_event = events[event_index + 1] if event_index + 1 < len(events) else None
        end = next_event['time'] if next_event else final_time
        samples = [row for row in trace if event['time'] - 1e-8 <= row['t'] <= end + 1e-8]
        airborne = [row for row in samples if row['contacts'][side] == 0]
        support = _longest_run(samples, lambda row: row['contacts'][side] == 0
                              and row['contacts'][1-side] > 0
                              and row['normal_forces_n'][1-side] > 50.)
        clearance = max((row['foot_clearance_m'][side] for row in airborne), default=0.)
        landed = bool(next_event and samples and samples[-1]['contacts'][side] > 0
                      and samples[-1]['normal_forces_n'][side] > .5 and airborne)
        advance = (samples[-1]['feet'][side][0] - samples[0]['feet'][side][0]) if samples else 0.
        later_same_foot = next((future['time'] for future in events[event_index + 1:]
                               if future['to'] == event['to']), final_time)
        after = [row for row in trace if end - 1e-8 <= row['t'] <= later_same_foot + 1e-8]
        loaded = _longest_run(after, lambda row: row['contacts'][side] > 0
                             and row['normal_forces_n'][side] > 50.)
        expected = SIDES[len(steps) % 2]
        threshold = .03 if not steps else .06
        observed = (SIDES[side] == expected and support >= .1 - 1e-8 and clearance >= .01
                    and landed and advance >= threshold and loaded >= .1 - 1e-8)
        steps.append({'step_number': len(steps) + 1, 'swing_foot': SIDES[side],
                      'support_foot': SIDES[1-side], 'start_s': event['time'], 'end_s': end,
                      'completed_phase': next_event is not None,
                      'loaded_single_support_s': support,
                      'maximum_airborne_capsule_clearance_m': clearance,
                      'foot_body_advance_m': advance, 'minimum_required_advance_m': threshold,
                      'airborne_then_contact_observed': landed,
                      'subsequent_loaded_contact_s': loaded,
                      'measured_step_accepted': bool(observed)})
    chatter = {}
    for side, name in enumerate(SIDES):
        eligible = airborne = 0
        eligible_s = airborne_s = 0.
        by_phase = []
        for index, row in enumerate(trace[:-1]):
            duration = max(0., trace[index + 1]['t'] - row['t'])
            if not by_phase or by_phase[-1]['phase'] != row['phase']:
                by_phase.append({'phase': row['phase'], 'start_s': row['t'], 'end_s': row['t'],
                                 'eligible_samples': 0, 'airborne_samples': 0,
                                 'eligible_duration_s': 0., 'airborne_duration_s': 0.})
            phase = by_phase[-1]
            phase['end_s'] = trace[index + 1]['t']
            if row['phase'] != 'swing_' + name:
                eligible += 1
                eligible_s += duration
                phase['eligible_samples'] += 1
                phase['eligible_duration_s'] += duration
                if row['contacts'][side] == 0:
                    airborne += 1
                    airborne_s += duration
                    phase['airborne_samples'] += 1
                    phase['airborne_duration_s'] += duration
        chatter[name] = {'airborne_samples': airborne, 'sampled_airborne_duration_s': airborne_s,
                         'eligible_non_swing_samples': eligible,
                         'eligible_non_swing_duration_s': eligible_s,
                         'airborne_fraction_of_eligible_time': airborne_s / eligible_s if eligible_s else 0.,
                         'by_phase': by_phase}
    six_steps = (len(steps) == 6 and all(step['measured_step_accepted'] for step in steps)
                 and [event['to'] for event in events] == EXPECTED_PHASES
                 and final_root[0] - initial_root[0] >= .17
                 and abs(final_root[1] - initial_root[1]) <= .03)
    report.update(measured_steps=steps, six_step_sequence_observed=bool(six_steps),
                  all_six_steps_measured=bool(len(steps) == 6 and all(
                      step['measured_step_accepted'] for step in steps)),
                  contact_chatter=chatter,
                  contact_chatter_method='Left-endpoint state durations between consecutive 0.004 s observations; final snapshot has no duration. Samples are not unique incidents.')
    return report
