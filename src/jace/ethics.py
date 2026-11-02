from __future__ import annotations

import re

from .models import EthicalAssessment


_HARM_PATTERNS = {
    "violence or physical injury": r"\b(kill|murder|stab|shoot|strangle|attack|assault|hurt|injure|beat|poison)\b",
    "weapon or explosive use": r"\b(bomb|explosive|weapon|gun|ammunition|detonate)\b",
    "destructive intent": r"\b(destroy|burn down|sabotage|wipe out|eradicate)\b",
}
_PREVENTION_MARKERS = re.compile(r"\b(prevent|avoid|stop|de-escalat|protect|safely|safety|defend against)\b", re.I)
_RESOURCE_MARKERS = re.compile(r"\b(waste|discard|throw away|consume|use up|hoard|buy more|maximum power)\b", re.I)
_SECRET_PATTERNS = [
    re.compile(r"\b(?:api[_ -]?key|password|token|secret)\s*[:=]\s*\S+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


def assess(text: str) -> EthicalAssessment:
    """Apply a conservative, explainable first-pass policy gate.

    This is a policy boundary, not a claim that regex can understand ethics. A
    production model can add evidence, but it must not bypass this gate.
    """
    lowered = text.lower()
    reasons: list[str] = []
    harmful = []
    for label, pattern in _HARM_PATTERNS.items():
        if re.search(pattern, lowered):
            harmful.append(label)

    prevention = bool(_PREVENTION_MARKERS.search(text))
    if harmful and not prevention:
        reasons.extend(f"Detected {item}." for item in harmful)
        return EthicalAssessment(
            allowed=False,
            ahimsa_score=0.0,
            aparigraha_score=0.8,
            risk_level="high",
            reasons=reasons,
            safer_alternative="I can help prevent harm, de-escalate, create distance, or contact appropriate emergency support.",
        )

    if harmful and prevention:
        reasons.append("The request contains harm-related language but is framed as prevention or protection.")

    aparigraha_score = 0.45 if _RESOURCE_MARKERS.search(text) else 0.85
    if aparigraha_score < 0.6:
        reasons.append("The request may involve avoidable resource use or accumulation.")

    return EthicalAssessment(
        allowed=True,
        ahimsa_score=0.85 if not harmful else 0.65,
        aparigraha_score=aparigraha_score,
        risk_level="medium" if harmful or aparigraha_score < 0.6 else "low",
        reasons=reasons or ["No direct high-risk harm pattern detected."],
    )


def sanitise_memory(text: str) -> tuple[str | None, list[str]]:
    """Return redacted memory text, or ``None`` when it should not be stored."""
    assessment = assess(text)
    if not assessment.allowed:
        return None, ["Memory rejected by Ahimsa alignment filter."]

    clean = text.strip()
    notes: list[str] = []
    for pattern in _SECRET_PATTERNS:
        clean, count = pattern.subn("[REDACTED SECRET]", clean)
        if count:
            notes.append("Potential credential redacted before persistence.")
    if not clean:
        return None, ["Empty memory is not persisted."]
    return clean, notes
