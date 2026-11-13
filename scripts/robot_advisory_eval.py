"""Synthetic advisory benchmark collection, never a robot-control safety gate."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path

LANGUAGES = {'en', 'hi', 'gu'}
SCOPE = ('Synthetic authored multilingual prompts, not validated translations or Agama texts. '
         'Recorded local lexical decisions are not semantic correctness or robot safety scores. '
         'No autonomous control, external model call, corpus admission or release qualification.')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


def validate_cases(cases):
    if not isinstance(cases, list) or not 1 <= len(cases) <= 90:
        raise ValueError('one to 90 cases required')
    ids, scenarios = set(), {}
    for case in cases:
        if not isinstance(case, dict) or set(case) != {'id', 'scenario', 'language', 'principle', 'prompt', 'rubric'}:
            raise ValueError('invalid benchmark case schema')
        for key, limit in [('id', 100), ('scenario', 80), ('principle', 80), ('prompt', 4000), ('rubric', 2000)]:
            value = case[key]
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError('invalid case text')
        if not re.fullmatch(r'[a-z0-9_-]+', case['scenario']) or not isinstance(case['language'], str) or case['language'] not in LANGUAGES:
            raise ValueError('invalid scenario or language')
        if case['id'] != case['scenario'] + '-' + case['language'] or case['id'] in ids:
            raise ValueError('duplicate or mismatched case identity')
        ids.add(case['id'])
        group = scenarios.setdefault(case['scenario'], [])
        if group and (case['rubric'], case['principle']) != (group[0]['rubric'], group[0]['principle']):
            raise ValueError('parallel cases must use the same rubric and principle')
        group.append(case)
    if any({c['language'] for c in group} != LANGUAGES for group in scenarios.values()):
        raise ValueError('every scenario requires English, Hindi and Gujarati cases')
    return cases


def summarize(cases, outputs):
    """Preserve missing outputs in coverage; never infer compliance from words."""
    validate_cases(cases)
    ids = {case['id'] for case in cases}
    if not isinstance(outputs, dict) or set(outputs) - ids:
        raise ValueError('unknown saved output IDs')
    rows = []
    for case in cases:
        value = outputs.get(case['id'])
        if case['id'] in outputs:
            if not isinstance(value, dict) or set(value) != {'response', 'lexical_allowed', 'action_proposed'}:
                raise ValueError('invalid saved output')
            if not isinstance(value['response'], str) or not value['response'].strip() or len(value['response']) > 32768:
                raise ValueError('response must be bounded nonempty text')
            if type(value['lexical_allowed']) is not bool or type(value['action_proposed']) is not bool:
                raise ValueError('invalid diagnostic flags')
        rows.append({'id': case['id'], 'language': case['language'], 'output_present': value is not None,
                     'review_binding_sha256': digest({'case': case, 'output': value}),
                     'human_review': 'not_performed'})
    return {'case_count': len(cases), 'output_count': len(outputs),
            'missing_output_ids': [r['id'] for r in rows if not r['output_present']],
            'cases': rows, 'semantic_quality_verified': False, 'robot_control_authorized': False,
            'scope': SCOPE}


def collect_local(cases):
    """Use a fresh empty memory database per prompt and an explicit local reasoner."""
    validate_cases(cases)
    from jace.engine import CognitiveEngine
    from jace.reasoner import LocalReasoner
    outputs = {}
    with tempfile.TemporaryDirectory(prefix='jace-robot-advisory-') as directory:
        for index, case in enumerate(cases):
            engine = CognitiveEngine(db_path=Path(directory) / f'{index}.sqlite3',
                                     canonical_path='', reasoner=LocalReasoner())
            try:
                result = engine.think('synthetic-benchmark', case['prompt'])
                outputs[case['id']] = {'response': result.response,
                                      'lexical_allowed': result.ethical_assessment.allowed,
                                      'action_proposed': result.action is not None}
            finally:
                engine.close()
    return outputs
