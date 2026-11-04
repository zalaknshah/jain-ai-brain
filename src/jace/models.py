from __future__ import annotations

import hashlib
import json

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EthicalAssessment:
    allowed: bool
    ahimsa_score: float
    aparigraha_score: float
    risk_level: str
    reasons: list[str] = field(default_factory=list)
    safer_alternative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Perspective:
    index: int
    sanskrit: str
    label: str
    conclusion: str
    confidence: float
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalEntry:
    entry_id: str
    title: str
    principle: str
    guidance: str
    source: str
    tags: list[str] = field(default_factory=list)
    work: str | None = None
    language: str = "en"
    edition: str | None = None
    location: str | None = None
    license: str | None = None
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Memory:
    memory_id: int
    user_id: str
    content: str
    created_at: str
    source: str = "user"
    updated_at: str | None = None
    expires_at: str | None = None
    memory_scope: str = "default"

    @property
    def revision(self) -> str:
        """Fingerprint of this complete stored state, not a secret or version clock."""
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode('ascii')).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "revision": self.revision}


@dataclass(frozen=True)
class ActionProposal:
    action: str
    parameters: dict[str, Any]
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThoughtResult:
    request_id: str
    user_id: str
    input: str
    response: str
    ethical_assessment: EthicalAssessment
    perspectives: list[Perspective]
    canonical_evidence: list[CanonicalEntry]
    memories_used: list[Memory]
    action: ActionProposal | None
    created_at: str
    memory_scope: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "memory_scope": self.memory_scope,
            "input": self.input,
            "response": self.response,
            "ethical_assessment": self.ethical_assessment.to_dict(),
            "perspectives": [item.to_dict() for item in self.perspectives],
            "canonical_evidence": [item.to_dict() for item in self.canonical_evidence],
            "memories_used": [item.to_dict() for item in self.memories_used],
            "action": self.action.to_dict() if self.action else None,
            "created_at": self.created_at,
        }
