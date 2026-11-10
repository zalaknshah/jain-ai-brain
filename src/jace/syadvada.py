from __future__ import annotations

from .models import Perspective


# These original editorial questions are not a translation or formalization of
# the seven predicates. The existing labels remain compatibility identifiers.
_ROWS = (
    ("syāt asti", "in some respect, it is",
     "Under which specified conditions, if any, would evidence support the claim?"),
    ("syāt nāsti", "in some respect, it is not",
     "Under which specified conditions, if any, would evidence count against the claim?"),
    ("syāt asti-nāsti", "in some respect, it is and is not",
     "If support and opposition concern different conditions, what are those conditions, and are separate claims being conflated?"),
    ("syāt avaktavya", "in some respect, it is indescribable",
     "Which terms or observations, if any, remain too unclear to assess?"),
    ("syāt asti-avaktavya", "in some respect, it is and is indescribable",
     "If any part is supported, what remains undefined or unassessed?"),
    ("syāt nāsti-avaktavya", "in some respect, it is not and is indescribable",
     "If any part is opposed, what remains undefined or unassessed?"),
    ("syāt asti-nāsti-avaktavya", "in some respect, it is, is not, and is indescribable",
     "Which supported, opposed and unresolved parts, if any, must be kept separate by condition, time or standpoint?"),
)


def evaluate(text: str, evidence: list[str] | None = None) -> list[Perspective]:
    """Return seven unanswered reflection prompts, not evaluated perspectives.

    The legacy function name, arguments, row order and labels are retained.
    Neither argument is analyzed. In particular, passage presence and lexical
    cues cannot establish support, contradiction, truth or numeric confidence.
    These original questions have not been qualified as Jain doctrinal analysis.
    """
    return [
        Perspective(
            index=index,
            sanskrit=sanskrit,
            label=label,
            conclusion="Not evaluated; no claim about support, contradiction or truth is made.",
            confidence=None,
            basis="Fixed editorial reflection prompt; input and evidence are not analyzed. Legacy labels are not validated doctrinal analysis.",
            prompt=prompt,
            status="not_evaluated",
        )
        for index, (sanskrit, label, prompt) in enumerate(_ROWS, 1)
    ]
