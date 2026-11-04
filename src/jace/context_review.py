"""Explicit context selection contracts, not semantic review or permission tokens."""
from __future__ import annotations

import hashlib
import json
import uuid
from urllib.parse import urlsplit

from .model_output import checked_text
from .memory import validate_memory_revision
from .memory_scope import validate_memory_scope
from .reasoner import HttpJsonReasoner, LocalReasoner, _model_endpoint

MAX_CONTEXT_BYTES = 48 * 1024
MAX_PREVIEW_BYTES = 64 * 1024
MAX_SELECTED = 5
LIMITS = [
    'Context preview performs no model call, learning or action.',
    'Selections and confirmation are caller assertions, not proof of human review or semantic support.',
    'Only selected current source records and owned scoped unexpired memories are supplied; no automatic supplements.',
    'Byte and character budgets are not tokenizer-level token or process resource guarantees.',
    'Already captured or transmitted context cannot be revoked by later deletion, expiry or configuration changes.',
]


def fingerprint(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def bounded_payload(value, limit: int, name: str) -> None:
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > limit:
        raise ValueError(f'{name} exceeds its byte budget; use a narrower question or smaller selection')


def question(user_id, request, memory_scope):
    checked_text(user_id, 'user ID', 256)
    checked_text(request, 'input', 10000)
    request = request.strip()
    memory_scope = validate_memory_scope(memory_scope)
    return request, memory_scope, fingerprint({'user_id':user_id,'input':request,'memory_scope':memory_scope})


def source_selection(entry) -> dict:
    return {'entry_id': entry.entry_id, 'revision': fingerprint(entry.to_dict())}


def memory_selection(memory) -> dict:
    return {'memory_id': memory.memory_id, 'revision': memory.revision}


def selections(value, kind: str) -> list[dict]:
    field = 'entry_id' if kind == 'source' else 'memory_id'
    if not isinstance(value, list) or len(value) > MAX_SELECTED:
        raise ValueError(f'{kind} selections must be a list of at most five entries')
    seen = set()
    result = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {field, 'revision'}:
            raise ValueError(f'invalid {kind} selection fields')
        ident = row[field]
        if kind == 'source':
            checked_text(ident, 'selected source ID', 128)
        elif type(ident) is not int or not 1 <= ident <= 2**63 - 1:
            raise ValueError('selected memory ID must be a positive 64-bit integer')
        validate_memory_revision(row['revision'])
        if ident in seen:
            raise ValueError(f'duplicate {kind} selection')
        seen.add(ident)
        result.append({field: ident, 'revision': row['revision']})
    return result


def reasoner_snapshot(reasoner) -> tuple[dict, tuple | None]:
    # Arbitrary custom/subclass reasoners cannot claim local or declared HTTP
    # behavior. They remain supported by the legacy think path only.
    if type(reasoner) is LocalReasoner:
        value = {'kind':'local','display_target':'Local rule-based response; no provider'}
        return {**value,'revision':fingerprint(value)}, None
    if type(reasoner) is HttpJsonReasoner:
        url = _model_endpoint(reasoner.url)
        model = checked_text(reasoner.model, 'model name', 256)
        parsed = urlsplit(url)
        display = f'{parsed.scheme}://{parsed.netloc} (model: {model})'
        checked_text(display, 'model destination', 2560)
        # Keep credential/path/query material inside the already configured
        # reasoner. An opaque process-local version changes when its target,
        # model, credential or transport instance changes; none is hashed into
        # a public value. This is not a new access token or persistent grant.
        api_key = reasoner.api_key
        if not isinstance(api_key, str) or len(api_key) > 4096 or any(ord(c)<32 or ord(c)==127 for c in api_key):
            raise ValueError('invalid configured model authorization')
        state = (url, model, api_key, id(reasoner._opener))
        if not hasattr(reasoner, '_review_configuration_identity'):
            # Non-authorizing state identity, like a request ID. Unlike id(),
            # it is not reused when Python releases an earlier instance.
            reasoner._review_configuration_identity = uuid.uuid4().hex
        if getattr(reasoner, '_review_configuration_state', None) != state:
            reasoner._review_configuration_state = state
            reasoner._review_configuration_version = getattr(reasoner, '_review_configuration_version', 0) + 1
        return {'kind':'http_json','display_target':display,
                'revision':fingerprint({'kind':'http_json','instance':reasoner._review_configuration_identity,
                                       'version':reasoner._review_configuration_version})}, (url, api_key, model)
    value = {'kind':'unavailable','display_target':'Custom reasoner is unavailable in selected-context mode'}
    return {**value,'revision':fingerprint(value)}, None


def reasoner_descriptor(reasoner) -> dict:
    return reasoner_snapshot(reasoner)[0]
