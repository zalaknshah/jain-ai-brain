"""Prepare explicit mixed-edition layers for human review, not training."""
from __future__ import annotations
import re
from scripts.prepare_translation_review import prepare, digest, METADATA

ROLES = {'root', 'rendering', 'translation', 'commentary', 'editorial'}


def prepare_layers(source: bytes, specification: dict) -> dict:
    """Keep edition layers separate while binding their declared relationships.

    No inference, translation, approval, IO or model calls. Caller must select
    exact spans and declare role/language and passage families. Links express
    hypotheses for review, never semantic equivalence or a verified translation.
    """
    if not isinstance(specification, dict) or set(specification) != {'source_sha256', 'metadata', 'layers'}:
        raise ValueError('invalid alignment specification')
    metadata = specification['metadata']
    if not isinstance(metadata, dict) or set(metadata) != METADATA - {'declared_source_language', 'text_role'}:
        raise ValueError('edition provenance required; language and role belong to each layer')
    layers = specification['layers']
    if not isinstance(layers, list) or not 1 <= len(layers) <= 64:
        raise ValueError('one to 64 layers required')
    tasks, ids, ranges = [], {}, []
    for layer in layers:
        if not isinstance(layer, dict) or set(layer) != {'id', 'byte_start', 'byte_end', 'locator', 'language', 'role', 'family', 'root_id'}:
            raise ValueError('invalid layer schema')
        if not isinstance(layer['role'], str) or layer['role'] not in ROLES:
            raise ValueError('invalid declared role')
        family = layer['family']
        if not isinstance(family, str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}', family):
            raise ValueError('invalid family ID')
        root = layer['root_id']
        if root is not None and (not isinstance(root, str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}', root)):
            raise ValueError('invalid root link')
        span = {key: layer[key] for key in ('id', 'byte_start', 'byte_end', 'locator')}
        task = prepare(source, {'source_sha256': specification['source_sha256'],
            'metadata': {**metadata, 'declared_source_language': layer['language'], 'text_role': layer['role']},
            'spans': [span]})['tasks'][0]
        if task['id'] in ids:
            raise ValueError('duplicate layer ID')
        start, end = span['byte_start'], span['byte_end']
        if any(start < old_end and old_start < end for old_start, old_end in ranges):
            raise ValueError('layer spans overlap; select separate explicit units')
        ranges.append((start, end))
        task['alignment'] = {'family': family, 'root_id': root, 'status': 'unreviewed'}
        ids[task['id']] = task
        tasks.append(task)
    for task in tasks:
        role = task['source']['metadata']['text_role']
        alignment = task['alignment']
        root_id = alignment['root_id']
        if role == 'root':
            if root_id is not None:
                raise ValueError('root layer cannot link to another root')
        else:
            root = ids.get(root_id)
            if root is None or root['source']['metadata']['text_role'] != 'root':
                raise ValueError('non-root layer must link to an explicit root')
            if alignment['family'] != root['alignment']['family']:
                raise ValueError('linked layers must share a passage family')
        alignment['root_source_binding_sha256'] = None if root_id is None else ids[root_id]['source_binding_sha256']
        task['alignment_binding_sha256'] = digest({'source_binding_sha256': task['source_binding_sha256'], 'alignment': alignment})
    return {'format': 'jace-private-layer-alignment-v1', 'tasks': tasks,
        'packet_sha256': digest(tasks), 'training_admitted': False,
        'runtime_admitted': False, 'public_release_approved': False,
        'scope': 'Operator-declared layers and relationships only. No language, OCR, rights, semantic equivalence or scholarship verified. Keep linked families together in any later dataset split; this preparation does not perform or authorize training.'}
