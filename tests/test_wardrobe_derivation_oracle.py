"""Original multi-row and seeded metamorphic checks, independent of planner helpers."""
import copy
import random
import unittest

from jace.wardrobe import build_wardrobe_plan
from wardrobe_derivation_oracle import CATEGORIES, verify_wardrobe_derivation


def row(label, category='tops', quantity=1, **changes):
    return dict(label=label, category=category, quantity=quantity, condition='ready',
                fit='fits', use='unused', preserve=False, ownership='mine') | changes


def fixture():
    return {'items': [row('મૂળ first', quantity=3), row('Second reserve', quantity=4),
                     row('Protected repair', quantity=2, preserve=True, condition='repair', fit='uncertain'),
                     row('Shared protected', quantity=2, ownership='shared', preserve=True, condition='repair'),
                     row('Repair unprotected', 'bottoms', 3, condition='repair', use='uncertain'),
                     row('Ready unknown use', 'bottoms', 2, use='uncertain'),
                     row('Daily coat', 'outerwear', 2, use='regular'),
                     row('Ill fitting shoes', 'footwear', 3, fit='does_not_fit'),
                     row('Other preserved', 'other', 2, preserve=True)],
            'minimum_ready': dict(tops=5, bottoms=3, outerwear=1, footwear=2, other=0)}


def candidate(value):
    plan = build_wardrobe_plan(value, include_derivation=True)
    verify_wardrobe_derivation(value, plan)
    return plan


def allocation(plan, category):
    return sum(step['possible_surplus_review_units'] for step in plan['item_steps'] if step['category'] == category)


class WardrobeDerivationOracleTests(unittest.TestCase):
    def test_original_multicategory_fixture_and_legacy_unchanged(self):
        value = fixture()
        before = copy.deepcopy(value)
        plan = candidate(value)
        self.assertEqual(value, before)
        self.assertEqual({k: v for k, v in plan.items() if k != 'derivation'}, build_wardrobe_plan(value))
        self.assertEqual([r['rule_priority'] for r in plan['derivation']['item_rules']], [5, 6, 2, 1, 3, 4, 7, 4, 2])
        self.assertEqual(plan['summary'], dict(declared_total_units=23, owned_ready_units=13,
                                             repair_review_units=5, uncertain_review_units=10, protected_units=6))

    def test_interleaved_categories_share_only_their_own_budget(self):
        value = {'items': [row('First tops', quantity=2), row('Between bottoms', 'bottoms', 3),
                           row('Second tops', quantity=4), row('Last tops', quantity=3),
                           row('Protected ready', quantity=2, preserve=True),
                           row('Unknown use ready', quantity=2, use='uncertain')],
                 'minimum_ready': {c: 8 if c == 'tops' else 2 if c == 'bottoms' else 0 for c in CATEGORIES}}
        plan = candidate(value)
        self.assertEqual([step['possible_surplus_review_units'] for step in plan['item_steps']],
                         [2, 1, 3, 0, 0, 0])
        self.assertEqual([rule['category_surplus_before'] for rule in plan['derivation']['item_rules']],
                         [5, 1, 3, 0, 0, 0])
        changed = copy.deepcopy(value)
        changed['items'][1]['quantity'] = 8
        changed_plan = candidate(changed)
        self.assertEqual(changed_plan['categories'][0], plan['categories'][0])
        for index in (0, 2, 3, 4, 5):
            self.assertEqual(changed_plan['item_steps'][index], plan['item_steps'][index])
            self.assertEqual(changed_plan['derivation']['item_rules'][index],
                             plan['derivation']['item_rules'][index])

    def test_nonvacuous_minimum_permutation_and_partial_split(self):
        value = {'items': [row('Alpha', quantity=3), row('Beta', quantity=4)],
                 'minimum_ready': {c: 5 if c == 'tops' else 0 for c in CATEGORIES}}
        baseline = candidate(value)
        self.assertEqual([s['possible_surplus_review_units'] for s in baseline['item_steps']], [2, 0])
        raised_input = copy.deepcopy(value)
        raised_input['minimum_ready']['tops'] = 6
        raised = candidate(raised_input)
        self.assertEqual(allocation(raised, 'tops'), 1)
        self.assertLess(allocation(raised, 'tops'), allocation(baseline, 'tops'))
        reversed_input = copy.deepcopy(value)
        reversed_input['items'].reverse()
        reversed_plan = candidate(reversed_input)
        by_label = lambda plan: {s['label']: s['possible_surplus_review_units'] for s in plan['item_steps']}
        self.assertEqual(by_label(baseline), {'Alpha': 2, 'Beta': 0})
        self.assertEqual(by_label(reversed_plan), {'Alpha': 0, 'Beta': 2})
        self.assertEqual(allocation(reversed_plan, 'tops'), allocation(baseline, 'tops'))
        split_input = copy.deepcopy(value)
        split_input['items'][0:1] = [row('Alpha left', quantity=1), row('Alpha right', quantity=2)]
        split_plan = candidate(split_input)
        self.assertEqual([s['possible_surplus_review_units'] for s in split_plan['item_steps']], [1, 1, 0])
        self.assertEqual(allocation(split_plan, 'tops'), allocation(baseline, 'tops'))
        self.assertEqual(split_plan['summary'], baseline['summary'])
        self.assertEqual(split_plan['categories'], baseline['categories'])

    def test_mutated_trace_and_plan_are_rejected(self):
        value = fixture()
        original = candidate(value)
        mutations = [
            (('derivation', 'inventory_sha256'), 'f' * 64),
            (('derivation', 'protocol'), True),
            (('derivation', 'basis'), 'verified_objects'),
            (('derivation', 'summary_contributors', 'declared_total_units', 0, 'row_ordinal'), 99),
            (('derivation', 'summary_contributors', 'owned_ready_units', 0, 'units'), 100),
            (('derivation', 'summary_contributors', 'declared_total_units', 0, 'row_ordinal'), True),
            (('derivation', 'item_rules', 0, 'allocated_units'), 3),
            (('derivation', 'item_rules', 1, 'allocated_units'), 2),
            (('derivation', 'item_rules', 1, 'category_surplus_before'), 2),
            (('derivation', 'item_rules', 2, 'rule_priority'), 3),
            (('derivation', 'item_rules', 2, 'rule'), 'repair_review'),
            (('derivation', 'item_rules', 3, 'rule'), 'preserve'),
            (('derivation', 'item_rules', 0, 'ready_counted'), 1),
            (('derivation', 'item_rules', 0, 'declared_fields', 'preserve'), 0),
            (('derivation', 'categories', 0, 'remaining_surplus_budget'), -1),
            (('derivation', 'categories', 0, 'initial_surplus_budget'), 3),
            (('derivation', 'categories', 0, 'ready_contributors', 0, 'units'), 4),
            (('summary', 'owned_ready_units'), 14),
            (('summary', 'protected_units'), 5),
            (('categories', 0, 'shortfall_units'), True),
            (('categories', 1, 'minimum_ready'), 4),
            (('item_steps', 0, 'quantity'), 4),
            (('item_steps', 1, 'possible_surplus_review_units'), 2),
            (('item_steps', 2, 'decision'), 'repair_review'),
            (('actions_executed',), 0),
            (('inventory_applied', 'items', 0, 'quantity'), 4),
        ]
        for path, replacement in mutations:
            with self.subTest(path=path):
                plan = copy.deepcopy(original)
                target = plan
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                with self.assertRaises(AssertionError):
                    verify_wardrobe_derivation(value, plan)
        # Mutually consistent corruption still cannot override original declarations.
        plan = copy.deepcopy(original)
        plan['item_steps'][1]['possible_surplus_review_units'] = 2
        plan['item_steps'][1]['decision'] = 'review_possible_surplus'
        plan['derivation']['item_rules'][1].update(allocated_units=2, category_surplus_before=2,
                                                 rule='review_possible_surplus', rule_priority=5)
        plan['derivation']['categories'][0]['allocated_surplus_review_units'] = 4
        with self.assertRaises(AssertionError):
            verify_wardrobe_derivation(value, plan)

    def test_trace_schema_and_order_corruption(self):
        value = fixture()
        original = candidate(value)
        for key in original['derivation']:
            plan = copy.deepcopy(original)
            del plan['derivation'][key]
            with self.subTest(missing=key), self.assertRaises(AssertionError):
                verify_wardrobe_derivation(value, plan)
        for key in ('categories', 'item_rules'):
            plan = copy.deepcopy(original)
            plan['derivation'][key].reverse()
            with self.subTest(reversed=key), self.assertRaises(AssertionError):
                verify_wardrobe_derivation(value, plan)
        plan = copy.deepcopy(original)
        plan['derivation']['summary_contributors']['declared_total_units'].append({'row_ordinal': 10, 'units': 1})
        with self.assertRaises(AssertionError):
            verify_wardrobe_derivation(value, plan)
        plan = copy.deepcopy(original)
        plan['derivation']['item_rules'][0]['invented'] = 0
        with self.assertRaises(AssertionError):
            verify_wardrobe_derivation(value, plan)

    def test_original_inventory_is_strictly_validated(self):
        original = fixture()
        plan = candidate(original)
        for path, replacement in [(('items', 0, 'quantity'), True), (('items', 0, 'preserve'), 0),
                                  (('minimum_ready', 'tops'), 5.0), (('items', 0, 'category'), 'shirt'),
                                  (('items', 0, 'label'), ' Shared protected '),
                                  (('items', 0, 'ownership'), 'self')]:
            value = copy.deepcopy(original)
            target = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            with self.subTest(path=path), self.assertRaises(AssertionError):
                verify_wardrobe_derivation(value, plan)

    def test_seeded_constructed_nonzero_budget_relations(self):
        rng = random.Random(920137)
        coverage = dict(nonzero_baselines=0, raised_minimum_changes=0, permutation_changes=0,
                        partial_splits=0, unrelated_category_isolation=0)
        for trial in range(40):
            category, unrelated = rng.sample(CATEGORIES, 2)
            a, b, protected = rng.randint(3, 12), rng.randint(3, 12), rng.randint(1, 8)
            budget = rng.randint(1, min(a, b) - 1)
            minimum = protected + a + b - budget
            value = {'items': [row(f'Constructed {trial} Alpha', category, a),
                               row(f'Constructed {trial} Other', unrelated, rng.randint(3, 8)),
                               row(f'Constructed {trial} Beta', category, b),
                               row(f'Constructed {trial} Protected', category, protected, preserve=True)],
                     'minimum_ready': {c: minimum if c == category else 1 if c == unrelated else 0
                                       for c in CATEGORIES}}
            baseline = candidate(value)
            self.assertEqual(allocation(baseline, category), budget)
            self.assertEqual(baseline['item_steps'][0]['possible_surplus_review_units'], budget)
            self.assertEqual(baseline['item_steps'][2]['possible_surplus_review_units'], 0)
            coverage['nonzero_baselines'] += 1

            raised_input = copy.deepcopy(value)
            increment = rng.randint(1, budget)
            raised_input['minimum_ready'][category] += increment
            raised = candidate(raised_input)
            self.assertEqual(allocation(raised, category), budget - increment)
            self.assertLess(allocation(raised, category), allocation(baseline, category))
            self.assertEqual(raised['item_steps'][1], baseline['item_steps'][1])
            coverage['raised_minimum_changes'] += 1

            swapped_input = copy.deepcopy(value)
            swapped_input['items'][0], swapped_input['items'][2] = swapped_input['items'][2], swapped_input['items'][0]
            swapped = candidate(swapped_input)
            by_label = lambda plan: {s['label']: s['possible_surplus_review_units'] for s in plan['item_steps']}
            self.assertNotEqual(by_label(swapped), by_label(baseline))
            self.assertEqual(by_label(swapped)[value['items'][0]['label']], 0)
            self.assertEqual(by_label(swapped)[value['items'][2]['label']], budget)
            self.assertEqual(allocation(swapped, category), allocation(baseline, category))
            self.assertEqual(swapped['item_steps'][1], baseline['item_steps'][1])
            coverage['permutation_changes'] += 1

            split_input = copy.deepcopy(value)
            source = split_input['items'][0]
            split_input['items'][0:1] = [dict(source, label=source['label'] + ' left', quantity=1),
                                        dict(source, label=source['label'] + ' right', quantity=a - 1)]
            split = candidate(split_input)
            self.assertEqual(split['item_steps'][0]['possible_surplus_review_units'], 1)
            self.assertEqual(split['item_steps'][1]['possible_surplus_review_units'], budget - 1)
            self.assertLess(budget - 1, a - 1)
            self.assertEqual(allocation(split, category), budget)
            self.assertEqual(split['summary'], baseline['summary'])
            self.assertEqual(split['categories'], baseline['categories'])
            self.assertEqual(split['item_steps'][2], baseline['item_steps'][1])
            coverage['partial_splits'] += 1

            isolated_input = copy.deepcopy(value)
            isolated_input['items'][1]['quantity'] += rng.randint(1, 5)
            isolated = candidate(isolated_input)
            for index in (0, 2, 3):
                self.assertEqual(isolated['item_steps'][index], baseline['item_steps'][index])
                self.assertEqual(isolated['derivation']['item_rules'][index],
                                 baseline['derivation']['item_rules'][index])
            category_index = CATEGORIES.index(category)
            self.assertEqual(isolated['derivation']['categories'][category_index],
                             baseline['derivation']['categories'][category_index])
            coverage['unrelated_category_isolation'] += 1
        self.assertEqual(coverage, dict(nonzero_baselines=40, raised_minimum_changes=40,
                                      permutation_changes=40, partial_splits=40,
                                      unrelated_category_isolation=40))
        self.constructed_coverage = coverage

    def test_seeded_multirow_metamorphic_relations(self):
        rng = random.Random(731904)
        coverage = dict(nonzero_baselines=0, raised_minimum_changes=0, permutation_changes=0)
        for trial in range(40):
            value = {'items': [row(f'Trial {trial} row {i}', rng.choice(CATEGORIES), rng.randint(2, 8),
                           condition=rng.choice(('ready', 'ready', 'repair', 'uncertain')),
                           fit=rng.choice(('fits', 'fits', 'does_not_fit', 'uncertain')),
                           use=rng.choice(('regular', 'occasional', 'unused', 'uncertain')),
                           preserve=rng.choice((True, False)),
                           ownership=rng.choice(('mine', 'mine', 'shared', 'others', 'uncertain')))
                       for i in range(12)], 'minimum_ready': {c: rng.randint(0, 8) for c in CATEGORIES}}
            baseline = candidate(value)
            coverage['nonzero_baselines'] += int(any(allocation(baseline, c) for c in CATEGORIES))
            # Higher declared minimum cannot create more available surplus.
            changed = copy.deepcopy(value)
            category = rng.choice(CATEGORIES)
            changed['minimum_ready'][category] += rng.randint(1, 5)
            raised = candidate(changed)
            coverage['raised_minimum_changes'] += int(allocation(raised, category) != allocation(baseline, category))
            self.assertLessEqual(allocation(raised, category), allocation(baseline, category))
            self.assertEqual(raised['summary'], baseline['summary'])
            # Permuting rows preserves aggregate counts and total eligible allocation,
            # though individual row recipients may change with entered order.
            changed = copy.deepcopy(value)
            rng.shuffle(changed['items'])
            permuted = candidate(changed)
            by_label = lambda plan: {s['label']: s['possible_surplus_review_units'] for s in plan['item_steps']}
            coverage['permutation_changes'] += int(by_label(permuted) != by_label(baseline))
            self.assertEqual(permuted['summary'], baseline['summary'])
            self.assertEqual(permuted['categories'], baseline['categories'])
            for c in CATEGORIES:
                self.assertEqual(allocation(permuted, c), allocation(baseline, c))
            # Adjacent split retains declarations and category total budget usage.
            changed = copy.deepcopy(value)
            index = rng.randrange(len(changed['items']))
            source = changed['items'][index]
            left = dict(source, quantity=1, label=source['label'] + ' A')
            right = dict(source, quantity=source['quantity'] - 1, label=source['label'] + ' B')
            changed['items'][index:index + 1] = [left, right]
            split = candidate(changed)
            self.assertEqual(split['summary'], baseline['summary'])
            self.assertEqual(split['categories'], baseline['categories'])
            for c in CATEGORIES:
                self.assertEqual(allocation(split, c), allocation(baseline, c))
            # Changing only one category's minimum leaves other category steps intact.
            for before, after in zip(baseline['item_steps'], raised['item_steps']):
                if before['category'] != category:
                    self.assertEqual(before, after)

        # Disclose the seed's limited allocation exercise; deterministic controls above
        # supply the actual changing-allocation cases rather than overstating fuzzing.
        self.assertEqual(coverage, dict(nonzero_baselines=1, raised_minimum_changes=0, permutation_changes=0))
        self.seeded_coverage = coverage


if __name__ == '__main__':
    unittest.main()
