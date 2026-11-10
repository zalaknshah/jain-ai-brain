"""Independent declaration-only oracle. No production imports or calculation helpers.

This checks arithmetic and rule provenance, not actual garments or semantic reasoning.
"""
import hashlib
import json
import unicodedata

CATEGORIES = ('tops', 'bottoms', 'outerwear', 'footwear', 'other')
SUMMARY = ('declared_total_units', 'owned_ready_units', 'repair_review_units',
           'uncertain_review_units', 'protected_units')
FIELDS = {'label', 'category', 'quantity', 'condition', 'fit', 'use', 'preserve', 'ownership'}
DECLARED = ('ownership', 'preserve', 'condition', 'fit', 'use')


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def exact(actual, expected, path='value'):
    """Recursive equality that does not equate bools, floats and integers."""
    require(type(actual) is type(expected), path + ': wrong type')
    if type(expected) is dict:
        require(actual.keys() == expected.keys(), path + ': wrong keys')
        for key in expected:
            exact(actual[key], expected[key], path + '.' + key)
    elif type(expected) is list:
        require(len(actual) == len(expected), path + ': wrong length')
        for i, (a, e) in enumerate(zip(actual, expected)):
            exact(a, e, path + '[' + str(i) + ']')
    else:
        require(actual == expected, path + ': wrong value')


def validate_original(value):
    require(type(value) is dict and set(value) == {'items', 'minimum_ready'}, 'inventory schema')
    rows, minimums = value['items'], value['minimum_ready']
    require(type(rows) is list and 1 <= len(rows) <= 30, 'inventory rows')
    require(type(minimums) is dict and set(minimums) == set(CATEGORIES), 'minimum schema')
    for n in minimums.values():
        require(type(n) is int and 0 <= n <= 50, 'minimum type/bounds')
    labels = set()
    for row in rows:
        require(type(row) is dict and set(row) == FIELDS, 'row schema')
        label = row['label']
        require(type(label) is str and 1 <= len(label) <= 60 and label == label.strip(), 'label')
        require(not any(unicodedata.category(c).startswith('C') for c in label), 'label control')
        identity = unicodedata.normalize('NFC', label).casefold()
        require(identity not in labels, 'duplicate label')
        labels.add(identity)
        require(type(row['quantity']) is int and 1 <= row['quantity'] <= 100, 'quantity')
        require(type(row['preserve']) is bool, 'preserve')
        for field, choices in [('category', CATEGORIES), ('condition', ('ready', 'repair', 'uncertain')),
                               ('fit', ('fits', 'does_not_fit', 'uncertain')),
                               ('use', ('regular', 'occasional', 'unused', 'uncertain')),
                               ('ownership', ('mine', 'shared', 'others', 'uncertain'))]:
            require(type(row[field]) is str and row[field] in choices, field)
    require(sum(r['quantity'] for r in rows) <= 300, 'total bound')
    return json.loads(json.dumps(value, ensure_ascii=False))


def verify_wardrobe_derivation(original, plan):
    inventory = validate_original(original)
    rows = inventory['items']
    require(type(plan) is dict, 'plan type')
    require(set(plan) == {'task', 'inventory_applied', 'action', 'actions_executed', 'summary',
                          'categories', 'item_steps', 'limits', 'derivation'}, 'plan schema')
    exact(plan['inventory_applied'], inventory, 'inventory_applied')
    exact(plan['task'], 'wardrobe_review')
    exact(plan['action'], None)
    exact(plan['actions_executed'], False)
    contributors = {key: [] for key in SUMMARY}
    ready_by_category = {category: [] for category in CATEGORIES}
    readiness = []
    for ordinal, row in enumerate(rows, 1):
        owned = row['ownership'] == 'mine'
        ready = owned and row['condition'] == 'ready' and row['fit'] == 'fits'
        readiness.append(ready)
        flags = (True, ready, owned and row['condition'] == 'repair',
                 owned and (row['condition'] == 'uncertain' or row['fit'] != 'fits' or row['use'] == 'uncertain'),
                 row['preserve'])
        entry = {'row_ordinal': ordinal, 'units': row['quantity']}
        for key, flag in zip(SUMMARY, flags):
            if flag:
                contributors[key].append(entry.copy())
        if ready:
            ready_by_category[row['category']].append(entry.copy())
    exact(plan['summary'], {key: sum(e['units'] for e in entries) for key, entries in contributors.items()}, 'summary')
    categories, budgets = [], {}
    for category in CATEGORIES:
        count = sum(e['units'] for e in ready_by_category[category])
        minimum = inventory['minimum_ready'][category]
        categories.append({'category': category, 'minimum_ready': minimum, 'owned_ready_units': count,
                           'shortfall_units': max(0, minimum - count)})
        budgets[category] = max(0, count - minimum)
    exact(plan['categories'], categories, 'categories')
    initial = budgets.copy()
    rules = []
    require(type(plan['item_steps']) is list and len(plan['item_steps']) == len(rows), 'steps length')
    for ordinal, (row, step, ready) in enumerate(zip(rows, plan['item_steps'], readiness), 1):
        category = row['category']
        before = budgets[category]
        allocated = 0
        if row['ownership'] != 'mine':
            priority, decision = 1, 'ownership_review'
        elif row['preserve']:
            priority, decision = 2, 'preserve'
        elif row['condition'] == 'repair':
            priority, decision = 3, 'repair_review'
        elif row['condition'] == 'uncertain' or row['fit'] != 'fits' or row['use'] == 'uncertain':
            priority, decision = 4, 'check_fit_or_condition'
        elif row['use'] == 'unused' and before > 0:
            priority, decision = 5, 'review_possible_surplus'
            allocated = min(row['quantity'], before)
        elif row['use'] == 'unused':
            priority, decision = 6, 'keep_for_declared_needs'
        else:
            priority, decision = 7, 'reuse'
        budgets[category] -= allocated
        require(type(step) is dict and set(step) == {'label', 'quantity', 'category', 'decision',
                                                    'possible_surplus_review_units', 'instruction'}, 'step schema')
        for field in ('label', 'quantity', 'category'):
            exact(step[field], row[field], 'step.' + field)
        exact(step['decision'], decision, 'decision')
        exact(step['possible_surplus_review_units'], allocated, 'allocation')
        require(type(step['instruction']) is str and bool(step['instruction'].strip()), 'instruction')
        rules.append({'row_ordinal': ordinal, 'rule_priority': priority, 'rule': decision,
                      'declared_fields': {k: row[k] for k in DECLARED}, 'ready_counted': ready,
                      'category_surplus_before': before, 'allocated_units': allocated,
                      'category_surplus_after': budgets[category]})
    trace_categories = []
    for category in categories:
        key = category['category']
        trace_categories.append({**category, 'ready_contributors': ready_by_category[key],
                                 'initial_surplus_budget': initial[key],
                                 'allocated_surplus_review_units': initial[key] - budgets[key],
                                 'remaining_surplus_budget': budgets[key]})
    trace = plan['derivation']
    require(type(trace) is dict and set(trace) == {'protocol', 'inventory_sha256', 'basis',
            'summary_contributors', 'categories', 'item_rules', 'limits'}, 'trace schema')
    expected = {'protocol': 1, 'inventory_sha256': hashlib.sha256(json.dumps(inventory,
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
                'basis': 'declared_inventory_rules', 'summary_contributors': contributors,
                'categories': trace_categories, 'item_rules': rules}
    exact({k: v for k, v in trace.items() if k != 'limits'}, expected, 'derivation')
    for limits in (trace['limits'], plan['limits']):
        require(type(limits) is list and bool(limits), 'limits')
        require(all(type(s) is str and s.strip() for s in limits), 'limits entries')
    return True
