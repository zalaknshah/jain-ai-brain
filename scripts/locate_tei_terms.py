"""Bounded, metadata-only literal TEI verse locator; never a translation engine."""
from __future__ import annotations
import hashlib
import re
import xml.etree.ElementTree as ET

TEI = '{http://www.tei-c.org/ns/1.0}'
MAX_OFFSETS_PER_GROUP = 64
MAX_OFFSETS_TOTAL = 512


def locate(source: bytes, expected_sha256: str, query: str, *, limit: int = 50, scope: str = "verse-groups") -> dict:
    """Find literal substrings in TEI body verse groups or marked base-text quotes.

    Results contain no source text. Character offsets refer to the precisely
    defined parsed selected-unit string, NOT original XML bytes. This is discovery only.
    """
    if not isinstance(source, bytes) or not 1 <= len(source) <= 2 * 1024 * 1024:
        raise ValueError('source must be 1 byte to 2 MiB')
    if scope not in ('verse-groups', 'marked-base-text-quotes'):
        raise ValueError('unsupported locator scope')
    actual = hashlib.sha256(source).hexdigest()
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256) or actual != expected_sha256:
        raise ValueError('source digest mismatch')
    if not isinstance(query, str) or not query.strip() or len(query) > 128:
        raise ValueError('query must be nonblank and at most 128 characters')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be 1 to 100')
    # Require UTF-8 before declaration screening; reject UTF-16/32 and DTDs.
    text = source.decode('utf-8-sig')
    if '\x00' in text or re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('DTD/entity declarations and null bytes forbidden')
    encoding = re.match(r'<\?xml[^?]*encoding\s*=\s*[\'"]([^\'"]+)', text, re.I)
    if encoding and encoding.group(1).lower() not in ('utf-8', 'utf8'):
        raise ValueError('only UTF-8 XML allowed')
    root = ET.fromstring(text)
    if root.tag != TEI + 'TEI':
        raise ValueError('TEI namespace root required')
    found, total, groups, offsets_used = [], 0, 0, 0
    def visit(node, in_body=False, depth=0):
        nonlocal total, groups, offsets_used
        if depth > 128:
            raise ValueError('XML nesting exceeds limit')
        in_body = in_body or node.tag == TEI + 'body'
        selected = (node.tag == TEI + 'lg') if scope == 'verse-groups' else (
            node.tag == TEI + 'quote' and node.get('type') == 'base-text')
        if in_body and selected:
            groups += 1
            # Include each descendant text slot once; no whitespace folding.
            parsed = ''.join(node.itertext())
            first = parsed.find(query)
            if first >= 0:
                total += 1
                if len(found) < limit:
                    budget = min(MAX_OFFSETS_PER_GROUP, MAX_OFFSETS_TOTAL - offsets_used)
                    offsets, pos = [], first
                    while pos >= 0 and len(offsets) < budget:
                        offsets.append(pos)
                        pos = parsed.find(query, pos + 1)
                    offsets_used += len(offsets)
                    # Never echo arbitrary n/xml:lang attributes or source text.
                    found.append({'group_index': groups,
                        'parsed_text_sha256': hashlib.sha256(parsed.encode()).hexdigest(),
                        'character_offsets': offsets, 'offsets_truncated': pos >= 0})
        for child in node:
            visit(child, in_body, depth + 1)
    visit(root)
    result = {'format': 'jace-literal-tei-locator-v1', 'source_sha256': actual,
        'query_sha256': hashlib.sha256(query.encode('utf-8')).hexdigest(), 'normalization': 'none', 'match_mode': 'literal-substring',
        'groups_examined': groups, 'matching_groups': total, 'truncated': total > limit,
        'matches': found, 'semantic_equivalence_verified': False,
        'translation_verified': False, 'training_admitted': False, 'runtime_admitted': False}

    if scope == 'marked-base-text-quotes':
        result['format'] = 'jace-literal-tei-marked-quotes-v1'
        result['scope'] = scope
        result['source_markup_verified'] = False
        result['units_examined'] = result.pop('groups_examined')
        result['matching_units'] = result.pop('matching_groups')
        for match in result['matches']:
            match['unit_index'] = match.pop('group_index')
    return result
