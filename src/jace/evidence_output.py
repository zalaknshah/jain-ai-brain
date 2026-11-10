"""Whole selected passage display, never generated claims or semantic scoring."""
from __future__ import annotations

from .model_output import checked_text, citation_records, source_integrity_reference
from .models import CanonicalEntry

OUTPUT_CONTRACT = 'whole_passages_v1'
INTRODUCTION = (
    'Selected source passages, not an answer. Their relevance, truth and support '
    'for any conclusion have not been established. These are complete admitted '
    'passages, not necessarily complete documents. Review, edition and licensing '
    'remain operator declarations.'
)


def render_selected_passages(evidence: list[CanonicalEntry]) -> str:
    """Fail closed instead of clipping, omitting, paraphrasing or falling back."""
    if not isinstance(evidence, list) or len(evidence) > 5 or any(
        not isinstance(entry, CanonicalEntry) for entry in evidence
    ):
        raise ValueError('evidence-only mode requires at most five source records')
    for entry in evidence:
        checked_text(entry.entry_id, 'source ID', 128)
    eligible = citation_records(evidence)
    if len(eligible) != len(evidence):
        raise ValueError('evidence-only mode requires eligible reviewed source records')
    lines = [INTRODUCTION]
    if not evidence:
        lines.append('No source passages selected.')
    for entry in evidence:
        # Unlike ordinary generated citation rendering, this mode displays the
        # edition and complete selected passage. Do not silently omit metadata.
        checked_text(entry.edition, 'source edition', 1000)
        lines.extend([
            f'[{entry.entry_id}] {entry.work}; {entry.source}; {entry.location}; '
            f'language: {entry.language}; edition: {entry.edition}; license: {entry.license}.',
            'Full selected passage:',
            entry.principle,
            source_integrity_reference(entry),
        ])
    result = '\n'.join(lines)
    checked_text(result, 'evidence-only response', 32768, allow_crlf=True)
    return result
