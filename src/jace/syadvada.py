from __future__ import annotations

import re

from .models import Perspective


_UNCERTAINTY = re.compile(r"\b(maybe|might|could|uncertain|unknown|depends|likely|possibly|perhaps)\b", re.I)
_NEGATION = re.compile(r"\b(not|no|never|without|cannot|can't|isn't|aren't)\b", re.I)
_OBSERVATION = re.compile(r"\b(i see|observed|measured|evidence|because|data|currently|today)\b", re.I)


def evaluate(text: str, evidence: list[str] | None = None) -> list[Perspective]:
    """Produce the seven qualified Syādvāda perspectives.

    The evaluator makes uncertainty explicit. It is intentionally transparent
    and deterministic so it can be used before or after an LLM response.
    """
    evidence = evidence or []
    has_uncertainty = bool(_UNCERTAINTY.search(text))
    has_negation = bool(_NEGATION.search(text))
    has_observation = bool(_OBSERVATION.search(text)) or bool(evidence)
    context = "given the available context"
    if has_uncertainty:
        context = "given the stated uncertainty and available context"

    rows = [
        ("syāt asti", "in some respect, it is", "A qualified possibility is supported", 0.62 if has_observation else 0.45),
        ("syāt nāsti", "in some respect, it is not", "A limitation, exception, or counter-case remains", 0.62 if has_negation else 0.42),
        ("syāt asti-nāsti", "in some respect, it is and is not", "The claim can hold under different conditions", 0.7 if has_uncertainty else 0.5),
        ("syāt avaktavya", "in some respect, it is indescribable", "The available information does not determine a complete description", 0.7 if not has_observation else 0.5),
        ("syāt asti-avaktavya", "in some respect, it is and is indescribable", "There is a plausible basis, but important details are unresolved", 0.68),
        ("syāt nāsti-avaktavya", "in some respect, it is not and is indescribable", "A counter-case is plausible while the boundary remains unresolved", 0.65),
        ("syāt asti-nāsti-avaktavya", "in some respect, it is, is not, and is indescribable", "The whole claim changes with standpoint, time, or missing evidence", 0.74 if has_uncertainty else 0.58),
    ]
    return [
        Perspective(
            index=index,
            sanskrit=sanskrit,
            label=label,
            conclusion=f"{conclusion} {context}.",
            confidence=confidence,
            basis="Textual cues and retrieved evidence; not an absolute predicate.",
        )
        for index, (sanskrit, label, conclusion, confidence) in enumerate(rows, 1)
    ]
