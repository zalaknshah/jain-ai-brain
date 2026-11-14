"""Bounded local fresh-study request serialization, never model/engine input."""
import json
import os
from dataclasses import fields
from .model_output import strict_json
from .fresh_private_study import ConsumerError, ExpectedPins, StudyDeclaration, consume

MAX_INPUT_BYTES = 8192
MAX_OUTPUT_BYTES = 1024 * 1024


def run_request(raw, *, bundle_directory, confirmed=False,
                allow_local_disclosure=False, review_noncandidates=False):
    """No IO before exact request/consent validation; no partial serialization.

    Expected pins are provided independently by the operator, not read from the
    bundle. Disclosure goes to the caller only; terminal retention is possible.
    Review opt-in is permission to inspect, never scholarly verification.
    """
    if (confirmed is not True or type(allow_local_disclosure) is not bool or
            type(review_noncandidates) is not bool):
        raise ConsumerError('Explicit private study confirmation required')
    if type(raw) is not bytes or not raw or len(raw) > MAX_INPUT_BYTES:
        raise ConsumerError('Invalid bounded fresh-study request')
    try:
        req = strict_json(raw)
        if type(req) is not dict:
            raise ValueError()
        if req.get('operation') == 'search':
            expected = {'operation', 'pins', 'declaration', 'query', 'limit'}
            if 'required_terms' in req:
                expected.add('required_terms')
                if type(req['required_terms']) is not list:
                    raise ValueError()
            if 'offset' in req:
                expected.add('offset')
        elif req.get('operation') == 'lookup_record':
            expected = {'operation', 'pins', 'declaration', 'record_id'}
            expected.update(k for k in ('before', 'after') if k in req)
        elif req.get('operation') == 'select':
            expected = {'operation', 'pins', 'declaration', 'xml_ids'}
        elif req.get('operation') in ('browse', 'review_queue'):
            expected = {'operation', 'pins', 'declaration', 'offset', 'limit'}
        else:
            expected = {'operation', 'pins', 'declaration', 'xml_id'}
            if req.get('operation') == 'lookup':
                expected.update(k for k in ('before', 'after') if k in req)
        if req.get('operation') in ('search', 'browse') and 'category' in req:
            expected.add('category')
            if type(req['category']) is not str:
                raise ValueError()
        if set(req) != expected:
            raise ValueError()
        if 'offset' in req and type(req['offset']) is not int:
            raise ValueError()
        for key in ('before', 'after'):
            if key in req and (type(req[key]) is not int or not 0 <= req[key] <= 8):
                raise ValueError()
        if type(req['pins']) is not dict or set(req['pins']) != {f.name for f in fields(ExpectedPins)}:
            raise ValueError()
        if type(req['declaration']) is not dict or set(req['declaration']) != {f.name for f in fields(StudyDeclaration)}:
            raise ValueError()
        if req['operation'] == 'inventory':
            if req['xml_id'] is not None or allow_local_disclosure or review_noncandidates:
                raise ValueError()
        elif req['operation'] == 'lookup':
            if not allow_local_disclosure or type(req['xml_id']) is not str or not 0 < len(req['xml_id']) <= 256:
                raise ValueError()
        elif req['operation'] == 'lookup_record':
            if not allow_local_disclosure or type(req['record_id']) is not str or not 0 < len(req['record_id']) <= 256:
                raise ValueError()
        elif req['operation'] in ('search', 'browse', 'select', 'review_queue'):
            if not allow_local_disclosure:
                raise ValueError()
        else:
            raise ValueError()
        pins = ExpectedPins(**req['pins'])
        declaration = StudyDeclaration(**req['declaration'])
    except (ValueError, TypeError, RecursionError):
        raise ConsumerError('Invalid request or missing local disclosure permission') from None
    if (os.name != 'posix' or any(not hasattr(os, n) for n in
            ('O_NOFOLLOW', 'O_DIRECTORY', 'O_CLOEXEC', 'O_NONBLOCK', 'geteuid')) or
            os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd or
            os.stat not in os.supports_follow_symlinks):
        raise ConsumerError('Fresh-study secure local IO requires POSIX primitives')
    result = consume(bundle_directory, pins=pins, declaration=declaration,
                     operation=req['operation'], xml_id=req.get('xml_id'), record_id=req.get('record_id'),
                     reviewed_noncandidates=review_noncandidates,
                     query=req.get('query'), limit=req.get('limit'), offset=req.get('offset'),
                     before=req.get('before', 0), after=req.get('after', 0), xml_ids=req.get('xml_ids'), category=req.get('category'), required_terms=req.get('required_terms'))
    wire = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n'
    if len(wire.encode('ascii')) > MAX_OUTPUT_BYTES:
        raise ConsumerError('Fresh-study output exceeds bounded limit')
    return wire
