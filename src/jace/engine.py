from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .canonical import CanonicalStore
from .cognitive_graph import CognitiveGraph
from .ethics import assess
from .memory import MemoryStore
from .models import ThoughtResult, utc_now
from .reasoner import Reasoner, configured_reasoner
from .syadvada import evaluate


class CognitiveEngine:
    def __init__(self, db_path: str | Path | None = None, canonical_path: str | Path | None = None, reasoner: Reasoner | None = None) -> None:
        self.canonical = CanonicalStore(canonical_path or os.getenv("JACE_CANONICAL_PATH"))
        actual_db_path = db_path or os.getenv("JACE_DB_PATH", "data/jace.sqlite3")
        self.memory = MemoryStore(actual_db_path)
        self.graph = CognitiveGraph(actual_db_path)
        self.graph.seed_canonical(self.canonical.all())
        self.reasoner = reasoner or configured_reasoner()

    def think(self, user_id: str, request: str) -> ThoughtResult:
        request = request.strip()
        if not user_id.strip():
            raise ValueError("user_id is required")
        if not request:
            raise ValueError("input is required")
        if len(request) > 10_000:
            raise ValueError("input must be 10,000 characters or fewer")

        assessment = assess(request)
        graph_hits = self.graph.retrieve(request, user_id, max_hops=2, max_nodes=12)
        evidence = self.canonical.search(request, limit=5)
        graph_entry_ids = {hit.source_id for hit in graph_hits if hit.node_type == "canonical" and hit.source_id}
        if graph_entry_ids:
            evidence = [entry for entry in self.canonical.all() if entry.entry_id in graph_entry_ids][:5]
        memories = self.memory.search(user_id, request, limit=5)
        graph_memory_ids = {int(hit.source_id) for hit in graph_hits if hit.node_type == "memory" and hit.source_id and hit.source_id.isdigit()}
        if graph_memory_ids:
            memories = [memory for memory in self.memory.list(user_id, 100) if memory.memory_id in graph_memory_ids][:5]
        perspectives = evaluate(request, [item.principle for item in evidence])
        response, action = self.reasoner.respond(request, assessment, perspectives, evidence, memories)
        return ThoughtResult(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            input=request,
            response=response,
            ethical_assessment=assessment,
            perspectives=perspectives,
            canonical_evidence=evidence,
            memories_used=memories,
            action=action,
            created_at=utc_now(),
        )

    def remember(self, user_id: str, content: str):
        if not user_id.strip():
            raise ValueError("user_id is required")
        memory, notes = self.memory.add(user_id, content)
        if memory:
            self.graph.add_memory(memory, self.canonical.all())
        return memory, notes

    def learn_from_conversation(self, user_id: str, content: str):
        """Extract only explicit preference/fact statements from a turn.

        Automatic learning is opt-in and deliberately conservative. Ordinary
        questions are not silently persisted as memories.
        """
        if not re.search(r"\b(remember|prefer|my name|i am|i live|we should|please note|do not forget)\b", content, re.I):
            return None, ["No explicit preference or fact detected; conversation was not persisted."]
        return self.remember(user_id, content)

    def forget_user(self, user_id: str) -> int:
        memories = self.memory.list(user_id, 100000)
        deleted = self.memory.delete_user(user_id)
        self.graph.remove_memories([memory.memory_id for memory in memories])
        return deleted

    def close(self) -> None:
        self.memory.close()
        self.graph.close()
