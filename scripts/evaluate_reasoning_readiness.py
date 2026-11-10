"""Observe actual local fallback answers; no Jain doctrinal correctness score.

These original application probes are NOT training/evaluation input to the CPU
router. They expose current behavior and preserve full outputs for human review.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner


def run() -> dict:
    path=ROOT/'evals/reasoning/cases.json'
    raw=path.read_bytes()
    cases=json.loads(raw)
    outcomes=[]
    with tempfile.TemporaryDirectory(prefix='jace-reasoning-diagnostic-') as directory:
        engine=CognitiveEngine(db_path=Path(directory)/'synthetic.sqlite3',canonical_path='',reasoner=LocalReasoner())
        try:
            for case in cases:
                result=engine.think('original-synthetic-diagnostic',case['query'])
                expected=case['expected_plan']
                source_question=case['family'] in ('doctrine','citation-diagnostic')
                outcomes.append({**case,'allowed':result.ethical_assessment.allowed,
                                 'expected_template_present':('Practical plan: '+expected) in result.response if expected else None,
                                 'reviewed_evidence_count':sum(x.verified is True for x in result.canonical_evidence),
                                 'retrieved_sample_ids':[x.entry_id for x in result.canonical_evidence],
                                 'source_limitation_present':'no reviewed canonical passage' in result.response,
                                 'generic_fallback_present':'does not have a tailored practical plan' in result.response,
                                 'source_question_fixture':source_question,
                                 'source_first_response_present':result.response.startswith((
                                     'Source evidence first:', 'I cannot give a source-grounded answer:',
                                     'I cannot present an invented quotation')),
                                 'practical_template_present':'Practical plan: ' in result.response,
                                 'response':result.response,
                                 'perspectives':[x.to_dict() for x in result.perspectives],
                                 'action':result.action.to_dict() if result.action else None})
        finally:engine.close()
    requested_templates=[x for x in outcomes if x['expected_plan']]
    source_questions=[x for x in outcomes if x['source_question_fixture']]
    return {'scope':'Original application diagnostics of current rule-based LocalReasoner with built-in unverified samples. No external model, imported scripture, scholarly rubric or Jain doctrinal correctness claim. The learned evidence router is not connected.',
            'fixture_sha256':hashlib.sha256(raw).hexdigest(), 'cases':outcomes,
            'observations':{'case_count':len(outcomes),
                            'requested_template_cases':len(requested_templates),
                            'requested_template_present':sum(x['expected_template_present'] for x in requested_templates),
                            'cases_with_reviewed_evidence':sum(x['reviewed_evidence_count']>0 for x in outcomes),
                            'generic_fallbacks':sum(x['generic_fallback_present'] for x in outcomes),
                            'source_question_cases':len(source_questions),
                            'source_first_responses':sum(x['source_first_response_present'] for x in source_questions),
                            'source_questions_with_practical_templates':sum(x['practical_template_present'] for x in source_questions),
                            'doctrinal_correctness':'not scored; reviewed source corpus and qualified independent review are absent'},
            'limits':['Keyword/template presence is not semantic accuracy or safety validation.',
                      'Seven generated perspective fields do not establish valid sevenfold reasoning.',
                      'The exact source limitation is measured as a string, not as proof that the rest of an answer is supported.',
                      'Source-first response markers measure routing/abstention, not a successful doctrinal answer or semantic reasoning.',
                      'These probes are a candid readiness diagnostic, not a representative or independently authored benchmark.']}


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
