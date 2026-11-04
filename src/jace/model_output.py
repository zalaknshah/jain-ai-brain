"""Mechanical output/source checks, not semantic entailment or model safety."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .models import CanonicalEntry

MAX_ANSWER_CHARS = 8000
MAX_CONTENT_CHARS = 16000
MAX_CITATIONS = 5
MAX_QUOTE_CHARS = 600
_UNSAFE_CONTROLS = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')


def checked_text(value, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or _UNSAFE_CONTROLS.search(value):
        raise ValueError(f'invalid {name}')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ValueError(f'invalid {name}') from error
    return value


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise ValueError('invalid JSON') from error


def citation_records(evidence: list[CanonicalEntry]) -> dict[str, CanonicalEntry]:
    result = {}
    seen = set()
    for entry in evidence:
        if entry.entry_id in seen:
            raise ValueError('ambiguous duplicate source IDs')
        seen.add(entry.entry_id)
        if entry.verified is not True:
            continue
        try:
            for name in ('work', 'source', 'language', 'location', 'license'):
                checked_text(getattr(entry, name), 'source ' + name, 1000)
            checked_text(entry.entry_id, 'source ID', 128)
            checked_text(entry.principle, 'source passage', 20000)
            if any(char in entry.entry_id for char in '[]\n\t'):
                continue
        except ValueError:
            continue
        result[entry.entry_id] = entry
    return result


@dataclass(frozen=True)
class MatchedCitation:
    entry: CanonicalEntry
    quote: str


@dataclass(frozen=True)
class CheckedModelOutput:
    answer: str
    citations: tuple[MatchedCitation, ...]

    def render(self) -> str:
        lines = ['Generated answer (not independently verified):', self.answer]
        if not self.citations:
            lines.append('Source check: no reviewed excerpt was supplied with this answer. It is not verified against a canonical passage.')
        else:
            lines.append('Matched retrieved excerpts: IDs and exact text were checked against this request\'s records. This does not establish that an excerpt supports the answer; source review and licensing remain operator declarations.')
            for citation in self.citations:
                entry = citation.entry
                lines.append(f'[{entry.entry_id}] {entry.work}; {entry.source}; {entry.location}; language: {entry.language}.')
                lines.append('Exact retrieved excerpt: ' + citation.quote)
        return '\n'.join(lines)


def check_model_output(content: str, evidence: list[CanonicalEntry]) -> CheckedModelOutput:
    checked_text(content, 'model content', MAX_CONTENT_CHARS)
    raw = strict_json(content)
    if not isinstance(raw, dict) or set(raw) != {'answer', 'citations'}:
        raise ValueError('model output requires only answer and citations')
    answer = checked_text(raw['answer'], 'answer', MAX_ANSWER_CHARS)
    # References are rendered below from local records, not arbitrary model labels.
    if re.search(r'\[[^\]\n]{1,128}\]', answer):
        raise ValueError('inline citation-like labels are not accepted')
    if not isinstance(raw['citations'], list) or len(raw['citations']) > MAX_CITATIONS:
        raise ValueError('invalid citation list')
    records = citation_records(evidence)
    seen = set(); citations = []
    for value in raw['citations']:
        if not isinstance(value, dict) or set(value) != {'entry_id', 'quote'}:
            raise ValueError('citation requires only entry_id and quote')
        entry_id = checked_text(value['entry_id'], 'citation ID', 128)
        quote = checked_text(value['quote'], 'quote', MAX_QUOTE_CHARS)
        if entry_id not in records or entry_id in seen or quote not in records[entry_id].principle:
            raise ValueError('unknown, duplicate, unreviewed or nonmatching citation')
        seen.add(entry_id); citations.append(MatchedCitation(records[entry_id], quote))
    return CheckedModelOutput(answer, tuple(citations))
