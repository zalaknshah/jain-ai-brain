from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .models import ActionProposal, CanonicalEntry, EthicalAssessment, Memory, Perspective


class Reasoner(Protocol):
    def respond(
        self,
        request: str,
        assessment: EthicalAssessment,
        perspectives: list[Perspective],
        evidence: list[CanonicalEntry],
        memories: list[Memory],
    ) -> tuple[str, ActionProposal | None]: ...


@dataclass
class LocalReasoner:
    """A predictable fallback that works without model weights or credentials."""

    def respond(self, request: str, assessment: EthicalAssessment, perspectives: list[Perspective], evidence: list[CanonicalEntry], memories: list[Memory]) -> tuple[str, ActionProposal | None]:
        if not assessment.allowed:
            return (
                f"I cannot help carry out that request because it presents a high risk of harm. {assessment.safer_alternative}",
                None,
            )

        guidance = evidence[0].guidance if evidence else "I will use the least harmful, least resource-intensive reversible option."
        memory_note = f" I also considered {len(memories)} relevant user memory item(s)." if memories else ""
        response = (
            "I am an engineered instrument, not a conscious being. "
            f"From the available standpoint, a careful response is: {guidance} "
            f"The seven perspectives indicate that the conclusion is context-dependent and should not be treated as absolute.{memory_note}"
        )
        action = self._action_for(request)
        return response, action

    @staticmethod
    def _action_for(request: str) -> ActionProposal | None:
        lowered = request.lower()
        if any(word in lowered for word in ("move", "walk", "navigate", "go to", "approach")):
            return ActionProposal(
                action="propose_safe_navigation",
                parameters={"speed": "slow", "clearance": "maximise", "avoid_contact": True},
            )
        if any(word in lowered for word in ("remember", "note that", "prefer", "my name")):
            return None
        return None


class HttpJsonReasoner:
    """Optional OpenAI-compatible chat-completions adapter.

    It is only selected when JACE_LLM_URL is configured. The engine still
    performs the local policy gate before invoking it.
    """

    def __init__(self, url: str, api_key: str = "", model: str = "") -> None:
        self.url = url
        self.api_key = api_key
        self.model = model or os.getenv("JACE_LLM_MODEL", "local-model")

    def respond(self, request: str, assessment: EthicalAssessment, perspectives: list[Perspective], evidence: list[CanonicalEntry], memories: list[Memory]) -> tuple[str, ActionProposal | None]:
        system = (
            "You are the JACE reasoning adapter. You are an engineered instrument, not conscious. "
            "Use Ahimsa, Aparigraha and qualified Syadvada reasoning. Never propose violence. "
            "Return concise plain text only. Do not invent retrieved sources."
        )
        context = {
            "request": request,
            "ethical_assessment": assessment.to_dict(),
            "seven_perspectives": [item.to_dict() for item in perspectives],
            "canonical_evidence": [item.to_dict() for item in evidence],
            "user_memories": [item.to_dict() for item in memories],
        }
        payload = json.dumps({"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(context)}], "temperature": 0.2}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            request_obj = urllib.request.Request(self.url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(request_obj, timeout=30) as result:
                body: dict[str, Any] = json.loads(result.read().decode())
            text = body["choices"][0]["message"]["content"]
            return str(text), LocalReasoner._action_for(request)
        except Exception:
            # A remote model is an enhancement, never a reason to lose the safe
            # local response path.
            return LocalReasoner().respond(request, assessment, perspectives, evidence, memories)


def configured_reasoner() -> Reasoner:
    url = os.getenv("JACE_LLM_URL", "").strip()
    return HttpJsonReasoner(url, os.getenv("JACE_LLM_API_KEY", "")) if url else LocalReasoner()
