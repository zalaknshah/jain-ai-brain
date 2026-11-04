"""Stateless, declared-option discussion preparation; no verdict or external action."""
from __future__ import annotations

import json
import unicodedata

from .ethics import assess
from .model_output import strict_json

MAX_INPUT_BYTES = 32 * 1024
MAX_OUTPUT_BYTES = 64 * 1024
FIELDS = {'decision', 'my_position', 'partner_position_reported', 'facts', 'constraints', 'options'}
FACT_FIELDS = {'reported_agreed', 'disputed', 'unknowns'}
CONSTRAINT_FIELDS = {'safety_concern', 'formal_deadline', 'binding_commitment'}
OPTION_FIELDS = {'label', 'description', 'my_fit', 'reported_partner_fit', 'reversibility', 'agreement', 'open_questions'}
CHOICES = ('yes', 'no', 'unknown')


def _text(value, field, maximum, *, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or value != value.strip():
        raise ValueError(f'{field} must be trimmed nonempty text of at most {maximum} characters')
    if any(unicodedata.category(character).startswith('C') or character in '\u2028\u2029' for character in value):
        raise ValueError(f'{field} must not contain control or format characters')
    return value


def _key(text):
    return unicodedata.normalize('NFC', text).casefold()


def _texts(value, field, *, count=8):
    if type(value) is not list or len(value) > count:
        raise ValueError(f'{field} must be a list of at most {count} text entries')
    result = [_text(item, field, 400) for item in value]
    if len({_key(item) for item in result}) != len(result):
        raise ValueError(f'{field} entries must be distinct, ignoring case and Unicode composition')
    return result


def _shape(value, fields, name):
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f'{name} requires exactly its documented fields')


def validate_worksheet(value):
    _shape(value, FIELDS, 'worksheet')
    decision = _text(value['decision'], 'decision', 500)
    mine = _text(value['my_position'], 'my_position', 500, nullable=True)
    partner = _text(value['partner_position_reported'], 'partner_position_reported', 500, nullable=True)
    _shape(value['facts'], FACT_FIELDS, 'facts')
    facts = {field: _texts(value['facts'][field], 'facts.' + field)
             for field in ('reported_agreed', 'disputed', 'unknowns')}
    seen = set()
    for entries in facts.values():
        keys = {_key(item) for item in entries}
        if seen & keys:
            raise ValueError('the same fact entry cannot appear in multiple status groups')
        seen.update(keys)
    _shape(value['constraints'], CONSTRAINT_FIELDS, 'constraints')
    if any(type(flag) is not bool for flag in value['constraints'].values()):
        raise ValueError('constraint flags must be explicit booleans')
    constraints = {field: value['constraints'][field] for field in ('safety_concern', 'formal_deadline', 'binding_commitment')}
    raw_options = value['options']
    if type(raw_options) is not list or not 2 <= len(raw_options) <= 4:
        raise ValueError('worksheet requires two through four candidate options')
    options, labels = [], set()
    for raw in raw_options:
        _shape(raw, OPTION_FIELDS, 'option')
        label = _text(raw['label'], 'option label', 60)
        if _key(label) in labels:
            raise ValueError('option labels must be distinct, ignoring case and Unicode composition')
        labels.add(_key(label))
        description = _text(raw['description'], 'option description', 600)
        for field in ('my_fit', 'reported_partner_fit', 'reversibility'):
            if type(raw[field]) is not str or raw[field] not in CHOICES:
                raise ValueError(f'option {field} must be yes, no or unknown')
        if type(raw['agreement']) is not str or raw['agreement'] not in ('not_discussed', 'reported_agreed', 'disputed'):
            raise ValueError('option agreement must be not_discussed, reported_agreed or disputed')
        if mine is None and raw['my_fit'] != 'unknown':
            raise ValueError('my_fit must remain unknown when my_position is not supplied')
        if partner is None and raw['reported_partner_fit'] != 'unknown':
            raise ValueError('reported_partner_fit must remain unknown when the reported partner position is not supplied')
        options.append({'label': label, 'description': description,
                        **{field: raw[field] for field in ('my_fit', 'reported_partner_fit', 'reversibility', 'agreement')},
                        'open_questions': _texts(raw['open_questions'], 'option open_questions', count=5)})
    result = {'decision': decision, 'my_position': mine, 'partner_position_reported': partner,
              'facts': facts, 'constraints': constraints, 'options': options}
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_INPUT_BYTES:
        raise ValueError('worksheet exceeds the 32 KiB input limit')
    free_text = [decision] + [position for position in (mine, partner) if position is not None]
    free_text.extend(item for entries in facts.values() for item in entries)
    for option in options:
        free_text.extend([option['label'], option['description'], *option['open_questions']])
    # Screen each field separately: a prevention phrase in another field cannot
    # qualify an independently harmful declaration. This is still only lexical.
    if any(not assess(text).allowed for text in free_text):
        raise ValueError('worksheet was rejected by the limited first-pass harm filter; no comparison was prepared')
    return result


def parse_worksheet(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError('worksheet input must be nonempty UTF-8 JSON of at most 32 KiB')
    try:
        value = strict_json(raw.decode('utf-8'))
    except (ValueError, UnicodeError):
        raise ValueError('worksheet input must be strict UTF-8 JSON without duplicate keys') from None
    return validate_worksheet(value)


def prepare_dispute(value):
    worksheet = validate_worksheet(value)
    constraints = worksheet['constraints']
    notices = []
    if constraints['safety_concern']:
        notices.append('You flagged a safety or coercion concern. Pause ordinary negotiation or a joint meeting; prioritize a safe setting and appropriate qualified support. This worksheet cannot assess the danger or establish that contact is safe.')
    if constraints['formal_deadline']:
        notices.append('You flagged a formal deadline. Verify the actual deadline and available steps with an appropriately qualified adviser. Preparing this worksheet does not extend a deadline or preserve legal rights.')
    if constraints['binding_commitment']:
        notices.append('You flagged a possible binding commitment. Review relevant agreements with appropriate qualified advice before changing them or making a new commitment. This worksheet does not interpret or approve a contract.')
    if not notices:
        notices.append('No special constraint was flagged by you. This does not establish that the situation is safe, deadline-free or without legal consequences.')
    questions = []
    if worksheet['my_position'] is None:
        questions.append('What outcome and constraints would you like your option to address? Your position remains unknown here.')
    if worksheet['partner_position_reported'] is None:
        questions.append('What position has your partner actually expressed, if known? Do not infer a motive or agreement from silence.')
    if not worksheet['facts']['reported_agreed']:
        questions.append('Are there any facts both parties explicitly describe as agreed? No agreed facts have been reported here.')
    if worksheet['facts']['disputed']:
        questions.append('What records or independent clarification could address each disputed claim? A disputed claim is not an established fact.')
    if worksheet['facts']['unknowns']:
        questions.append('Which listed unknowns would materially change the discussion? Identify how they could be clarified without treating a guess as evidence.')
    comparisons = []
    for option in worksheet['options']:
        prompts = []
        for field, subject in (('my_fit', 'your position'), ('reported_partner_fit', 'the reported partner position')):
            if option[field] == 'unknown':
                prompts.append(f'How, if at all, would this option address {subject}? The fit is explicitly unknown.')
            elif option[field] == 'no':
                prompts.append(f'You marked this option as not addressing {subject}. What would have to change? No acceptable compromise is inferred.')
            else:
                prompts.append(f'You marked this option as addressing {subject}. What evidence or clarification supports that assessment? This is your declaration, not verification.')
        if any(constraints.values()):
            prompts.append('A safety, deadline or commitment concern was flagged. Keep this as an unselected option for appropriate qualified review; no trial, meeting, delay or commitment is proposed.')
        elif option['reversibility'] == 'yes':
            prompts.append('You marked this option reversible. Identify the actual stopping conditions, effects and review point before considering a trial; reversibility is not verified or permission to proceed.')
        elif option['reversibility'] == 'no':
            prompts.append('You marked this option not reversible. Do not treat it as a small reversible trial; review consequences and required advice before any decision.')
        else:
            prompts.append('Reversibility is unknown. Clarify what could and could not be undone before considering a trial.')
        if constraints['safety_concern']:
            prompts.append('The entered agreement status does not establish current consent or safety. This worksheet does not propose contacting anyone to verify it.')
        elif option['agreement'] == 'reported_agreed':
            prompts.append('You reported agreement on this option. Confirm its exact scope and each relevant person’s current consent separately; this entry is not verified agreement or authorization.')
        elif option['agreement'] == 'disputed':
            prompts.append('You marked this option disputed. Preserve that disagreement and identify unresolved points; no consent or commitment is inferred.')
        else:
            prompts.append('You marked this option not discussed. No partner consent, acceptance or commitment is inferred.')
        comparisons.append({'option': option, 'declaration_source': 'user_reported',
                            'review_prompts': prompts, 'unanswered_questions': list(option['open_questions'])})
    result = {'task': 'dispute_preparation', 'protocol': 1,
              'status': 'qualified_review_needed' if any(constraints.values()) else 'preparation_only',
              'worksheet': worksheet, 'declaration_source': 'user_reported',
              'partner_position_verified': False, 'facts_independently_verified': False,
              'constraint_notices': notices, 'clarifying_questions': questions,
              'option_comparisons': comparisons, 'recommended_option': None,
              'action': None, 'actions_executed': False, 'saved': False, 'provider_called': False,
              'limits': [
                  'A worksheet built from your explicit entries, not learned reasoning, mediation, a verdict or legal advice.',
                  'Reported agreement, fact labels, fit and reversibility are your declarations. They do not establish truth, feasibility, safety, consent or another person’s motives.',
                  'Options stay in the entered order. There is no ranking, score, inferred compromise or recommended option.',
                  'No source retrieval, religious ruling, citation, memory read/write, model call, message, purchase, contract or robot action is performed.',
                  'The English pattern-based harm filter is limited and may miss harmful content or reject benign descriptions. Passing it is not a safety assessment.',
                  'The builder stores nothing. Your terminal, API client, proxy or other surrounding software may retain input/output; this is not a guarantee of system-wide erasure.',
              ]}
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_OUTPUT_BYTES:
        raise ValueError('prepared worksheet exceeds the 64 KiB output limit')
    return result
