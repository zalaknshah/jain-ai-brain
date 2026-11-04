"""Explicit clothing inventory and conservative review steps, not inferred needs."""
from __future__ import annotations

import json
import unicodedata

from .model_output import strict_json
from .models import Memory

INVENTORY_SOURCE = 'wardrobe_inventory_v1'
CATEGORIES = ('tops', 'bottoms', 'outerwear', 'footwear', 'other')
ITEM_FIELDS = {'label', 'category', 'quantity', 'condition', 'fit', 'use', 'preserve', 'ownership'}


def validate_inventory(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {'items', 'minimum_ready'}:
        raise ValueError('inventory requires exactly items and minimum_ready')
    needs = value['minimum_ready']
    if not isinstance(needs, dict) or set(needs) != set(CATEGORIES):
        raise ValueError('minimum_ready requires all five clothing categories')
    if any(type(n) is not int or not 0 <= n <= 50 for n in needs.values()):
        raise ValueError('each declared minimum must be an integer from 0 through 50')
    items = value['items']
    if not isinstance(items, list) or not 1 <= len(items) <= 30:
        raise ValueError('inventory requires 1 through 30 item rows')
    result, labels, total = [], set(), 0
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            raise ValueError('each item requires exactly label, category, quantity, condition, fit, use, preserve and ownership')
        label = item['label']
        if not isinstance(label, str) or not 1 <= len(label) <= 60 or label != label.strip() or any(unicodedata.category(c).startswith('C') for c in label):
            raise ValueError('item labels must be 1 through 60 trimmed characters without control/format characters')
        key = unicodedata.normalize('NFC', label).casefold()
        if key in labels:
            raise ValueError('item labels must be distinct, ignoring case and Unicode composition')
        labels.add(key)
        for field, allowed in (
            ('category', CATEGORIES), ('condition', ('ready', 'repair', 'uncertain')),
            ('fit', ('fits', 'does_not_fit', 'uncertain')), ('use', ('regular', 'occasional', 'unused', 'uncertain')),
            ('ownership', ('mine', 'shared', 'others', 'uncertain')),
        ):
            if not isinstance(item[field], str) or item[field] not in allowed:
                raise ValueError(f'invalid item {field}')
        if type(item['quantity']) is not int or not 1 <= item['quantity'] <= 100:
            raise ValueError('item quantity must be an integer from 1 through 100')
        if type(item['preserve']) is not bool:
            raise ValueError('preserve must be an explicit boolean choice')
        total += item['quantity']
        if total > 300:
            raise ValueError('declared quantities must total no more than 300 units')
        result.append({field: item[field] for field in ('label', 'category', 'quantity', 'condition', 'fit', 'use', 'preserve', 'ownership')})
    return {'items': result, 'minimum_ready': {category: needs[category] for category in CATEGORIES}}


def encode_inventory(inventory: dict) -> str:
    value = json.dumps({'version': 1, 'inventory': validate_inventory(inventory)}, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(value) > 10000:
        raise ValueError('encoded inventory exceeds the memory record limit')
    return value


def decode_inventory(memory: Memory) -> dict:
    if memory.source != INVENTORY_SOURCE or not isinstance(memory.content, str) or len(memory.content) > 10000:
        raise ValueError('not a bounded typed wardrobe inventory')
    value = strict_json(memory.content)
    if not isinstance(value, dict) or set(value) != {'version', 'inventory'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('invalid stored wardrobe inventory schema')
    return validate_inventory(value['inventory'])


def build_wardrobe_plan(value: dict) -> dict:
    inventory = validate_inventory(value)
    items, needs = inventory['items'], inventory['minimum_ready']
    ready = lambda item: item['ownership'] == 'mine' and item['condition'] == 'ready' and item['fit'] == 'fits'
    counts = {category: sum(item['quantity'] for item in items if item['category'] == category and ready(item)) for category in CATEGORIES}
    surplus = {category: max(0, counts[category] - needs[category]) for category in CATEGORIES}
    steps = []
    for item in items:
        quantity, category, label = item['quantity'], item['category'], item['label']
        review_quantity = 0
        if item['ownership'] != 'mine':
            decision = 'ownership_review'
            instruction = 'Leave these belongings unchanged. Confirm ownership and obtain the relevant owners’ agreement before handling, repairing or offering any item. These units do not count toward your owned-ready minimum.'
        elif item['preserve']:
            decision = 'preserve'
            instruction = 'Preserve these units as explicitly requested. Check fit, condition and care instructions before use; preserving an item does not establish that it is wearable.'
        elif item['condition'] == 'repair':
            decision = 'repair_review'
            instruction = 'Review whether an appropriate repair is feasible using suitable supplies already available. Check care instructions and skills needed; do not improvise hazardous repairs. No repair success, cost or material saving is assumed.'
        elif item['condition'] != 'ready' or item['fit'] != 'fits' or item['use'] == 'uncertain':
            decision = 'check_fit_or_condition'
            instruction = 'Set these units aside for your own fit, condition and use review. Uncertainty is not evidence that they should be discarded or replaced. Do not count unready or non-fitting units as meeting the ready minimum.'
        elif item['use'] == 'unused' and surplus[category] > 0:
            decision = 'review_possible_surplus'
            review_quantity = min(quantity, surplus[category])
            surplus[category] -= review_quantity
            instruction = (f'Up to {review_quantity} of these {quantity} declared units can be considered for a reversible surplus review while retaining the category minimum in this inventory snapshot. '
                           'This is not a donation or disposal recommendation. Check seasonal, work, health, belief and sentimental needs not represented here. '
                           'Only after your separate decision and a willing recipient’s acceptance could you consider offering suitable items. No transfer, purchase or contact is authorized.')
        elif item['use'] == 'unused':
            decision = 'keep_for_declared_needs'
            instruction = 'Keep these units available for review against your declared minimum. No surplus quantity is established by this inventory. Reassess needs and suitability before changing anything.'
        else:
            decision = 'reuse'
            instruction = 'Consider re-wearing and combining these suitable already-owned units. Try storage you already own, follow care instructions, and preserve necessary clothing. No new organizer or clothing purchase is proposed.'
        steps.append({'label': label, 'quantity': quantity, 'category': category, 'decision': decision,
                      'possible_surplus_review_units': review_quantity, 'instruction': instruction})
    return {'task': 'wardrobe_review', 'inventory_applied': inventory, 'action': None, 'actions_executed': False,
            'summary': {
                'declared_total_units': sum(item['quantity'] for item in items),
                'owned_ready_units': sum(counts.values()),
                'repair_review_units': sum(item['quantity'] for item in items if item['ownership'] == 'mine' and item['condition'] == 'repair'),
                'uncertain_review_units': sum(item['quantity'] for item in items if item['ownership'] == 'mine' and (item['condition'] == 'uncertain' or item['fit'] != 'fits' or item['use'] == 'uncertain')),
                'protected_units': sum(item['quantity'] for item in items if item['preserve']),
            },
            'categories': [{'category': category, 'minimum_ready': needs[category], 'owned_ready_units': counts[category],
                            'shortfall_units': max(0, needs[category] - counts[category])} for category in CATEGORIES],
            'item_steps': steps,
            'limits': [
                'Counts are user-declared units, not verified objects, measurements, material savings or an optimal wardrobe. Summary categories overlap and must not be added together.',
                'For footwear or sets, use one consistent unit such as a pair or set in both quantities and minimums. The planner cannot infer units or detect duplicate physical items under different labels.',
                'Minimums are your declarations, not assessed needs. Category shortfalls call for a needs/inventory review, not an instruction to buy.',
                'Surplus review only considers explicitly unused, owned, ready, fitting, unprotected units; it is allocated in entered row order and is not an optimized selection.',
                'No donation, disposal, ownership transfer, contact, purchase, repair or robot action is executed or authorized by this checklist.',
                'No learned reasoning, religious ruling, fiber/material classification, scholarly interpretation or verified environmental/health claim is supplied.',
            ]}
