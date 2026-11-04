from __future__ import annotations

import os
import json
import re
import uuid
from functools import wraps
from threading import RLock
from pathlib import Path

from .canonical import CanonicalStore
from .cognitive_graph import CognitiveGraph
from .ethics import assess
from .memory import MemoryStore
from .memory_scope import DEFAULT_SCOPE, validate_memory_scope
from .models import ActionProposal, ThoughtResult, utc_now
from .model_output import checked_text
from .practical import plan_for
from .reasoner import LocalReasoner, Reasoner, configured_reasoner
from .syadvada import evaluate
from .temporal import recall_time


def synchronized(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class CognitiveEngine:
    def __init__(self, db_path: str | Path | None = None, canonical_path: str | Path | None = None, reasoner: Reasoner | None = None) -> None:
        self._lock = RLock()
        canonical_source = canonical_path if canonical_path is not None else os.getenv("JACE_CANONICAL_PATH")
        self.canonical = CanonicalStore(canonical_source)
        actual_db_path = db_path or os.getenv("JACE_DB_PATH", "data/jace.sqlite3")
        self.memory = MemoryStore(actual_db_path)
        self.graph = CognitiveGraph(actual_db_path, connection=self.memory.connection)
        self.graph.seed_canonical(self.canonical.all())
        self.reasoner = reasoner or configured_reasoner()

    @synchronized
    def think(self, user_id: str, request: str, *, memory_scope: str = DEFAULT_SCOPE) -> ThoughtResult:
        memory_scope = validate_memory_scope(memory_scope)
        request = request.strip()
        if not user_id.strip():
            raise ValueError("user_id is required")
        if not request:
            raise ValueError("input is required")
        if len(request) > 10_000:
            raise ValueError("input must be 10,000 characters or fewer")

        assessment = assess(request)
        # Rejection is an engine boundary, not an instruction delegated to a model.
        if not assessment.allowed:
            response, _ = LocalReasoner().respond(request, assessment, [], [], [])
            return ThoughtResult(
                request_id=str(uuid.uuid4()), user_id=user_id, input=request,
                response=response, ethical_assessment=assessment,
                perspectives=evaluate(request), canonical_evidence=[],
                memories_used=[], action=None, created_at=utc_now(), memory_scope=memory_scope,
            )
        context_time = recall_time()
        graph_hits = self.graph.retrieve(request, user_id, max_hops=2, max_nodes=12, at=context_time, memory_scope=memory_scope)
        plan = plan_for(request)
        retrieval_query = request + (" " + plan.retrieval_terms if plan else "")
        evidence = self.canonical.search(retrieval_query, limit=5)
        # Preserve direct relevance order, then supplement from active graph
        # hits. Do not replace the whole result with file-order graph entries.
        by_id = {entry.entry_id: entry for entry in self.canonical.all()}
        seen = {entry.entry_id for entry in evidence}
        for hit in graph_hits:
            if hit.node_type == "canonical" and hit.source_id in by_id and hit.source_id not in seen and len(evidence) < 5:
                evidence.append(by_id[hit.source_id])
                seen.add(hit.source_id)
        memories = self.memory.search(user_id, request, limit=5, at=context_time, memory_scope=memory_scope)
        # Keep direct lexical relevance, then supplement in graph rank order.
        # Graph IDs never authorize access; recheck authoritative rows here.
        graph_memory_ids = [int(hit.source_id) for hit in graph_hits if hit.node_type == "memory"
                            and hit.source_id and hit.source_id.isascii() and hit.source_id.isdigit()
                            and len(hit.source_id) <= 19 and 1 <= int(hit.source_id) <= 2**63 - 1]
        seen_memories = {memory.memory_id for memory in memories}
        for memory in self.memory.selected(user_id, graph_memory_ids, at=context_time, memory_scope=memory_scope):
            if len(memories) >= 5:
                break
            if memory.memory_id not in seen_memories:
                memories.append(memory)
                seen_memories.add(memory.memory_id)
        perspectives = evaluate(request, [item.principle for item in evidence])
        try:
            response, action = self.reasoner.respond(request, assessment, perspectives, evidence, memories)
            checked_text(response, 'reasoner response', 32768)
            if action is not None:
                if not isinstance(action, ActionProposal) or action.requires_confirmation is not True or not isinstance(action.parameters, dict):
                    raise ValueError('reasoner actions must remain explicit confirmation-gated proposals')
                checked_text(action.action, 'action name', 128)
                if len(json.dumps(action.to_dict(), allow_nan=False).encode()) > 4096:
                    raise ValueError('action proposal exceeds size limit')
        except Exception:
            try:
                response, action = LocalReasoner().respond(request, assessment, perspectives, evidence, memories)
                response = 'The reasoning response failed validation. Using the local rule-based response.\n' + response
                checked_text(response, 'fallback response', 32768)
            except Exception:
                response, action = 'A response could not be safely formatted from the available context. Please review the configured source records or try a narrower request.', None
        # Apply the same first-pass boundary to generated text. This is not a
        # substitute for a production semantic safety evaluator.
        output_assessment = assess(response)
        if not output_assessment.allowed:
            assessment = output_assessment
            response, action = LocalReasoner().respond(request, assessment, perspectives, evidence, memories)
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
            memory_scope=memory_scope,
        )

    @synchronized
    def remember(self, user_id: str, content: str, *, expires_at: str | None = None, memory_scope: str = DEFAULT_SCOPE):
        if not user_id.strip():
            raise ValueError("user_id is required")
        with self.memory.connection:
            self.memory.connection.execute("BEGIN IMMEDIATE")
            memory, notes = self.memory.add(user_id, content, expires_at=expires_at, memory_scope=memory_scope, commit=False)
            if memory:
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def correct_memory(self, user_id: str, memory_id: int, content: str, *, expected_revision: str | None = None):
        self._validate_memory_identity(user_id, memory_id)
        with self.memory.connection:
            self.memory.connection.execute("BEGIN IMMEDIATE")
            self.memory.check_revision(user_id, memory_id, expected_revision)
            memory, notes = self.memory.replace(user_id, memory_id, content, commit=False)
            if memory:
                self.graph.remove_memories([memory_id], commit=False)
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def learn_from_conversation(self, user_id: str, content: str, *, memory_scope: str = DEFAULT_SCOPE):
        """Extract only explicit preference/fact statements from a turn.

        Automatic learning is opt-in and deliberately conservative. Ordinary
        questions are not silently persisted as memories.
        """
        memory_scope = validate_memory_scope(memory_scope)
        if not re.search(r"\b(remember|prefer|my name|i am|i live|we should|please note|do not forget)\b", content, re.I):
            return None, ["No explicit preference or fact detected; conversation was not persisted."]
        return self.remember(user_id, content, memory_scope=memory_scope)

    @synchronized
    def forget_user(self, user_id: str) -> int:
        # Reserve the writer transaction before taking the snapshot so other
        # engine processes cannot insert between the snapshot and deletion.
        with self.memory.connection:
            self.memory.connection.execute("BEGIN IMMEDIATE")
            memories = self.memory.list(user_id, None)
            self.graph.remove_memories([memory.memory_id for memory in memories], commit=False)
            self.graph.remove_legacy_orphans(user_id, commit=False)
            deleted = self.memory.delete_user(user_id, commit=False)
        return deleted

    @staticmethod
    def _validate_memory_identity(user_id: str, memory_id: int) -> None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('user_id is required')
        if isinstance(memory_id, bool) or not isinstance(memory_id, int) or not 1 <= memory_id <= 2**63 - 1:
            raise ValueError('memory_id must be a positive 64-bit integer')

    @synchronized
    def set_memory_expiration(self, user_id: str, memory_id: int, expires_at: str | None, *, expected_revision: str | None = None):
        self._validate_memory_identity(user_id, memory_id)
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            self.memory.check_revision(user_id, memory_id, expected_revision)
            memory = self.memory.set_expiration(user_id, memory_id, expires_at, commit=False)
        # Graph reads expiry from the owned memory row, never a separate copy.
        return memory

    @synchronized
    def preview_memory_deletion(self, user_id: str, memory_id: int) -> dict:
        self._validate_memory_identity(user_id, memory_id)
        return self.memory.deletion_preview(user_id, memory_id)

    @synchronized
    def forget_memory(self, user_id: str, memory_id: int, *, confirm_delete: bool = False,
                      confirm_unattributed_audit_cleanup: bool = False, expected_revision: str | None = None) -> int:
        self._validate_memory_identity(user_id, memory_id)
        if type(confirm_delete) is not bool or type(confirm_unattributed_audit_cleanup) is not bool:
            raise ValueError('deletion confirmations must be boolean')
        if not confirm_delete:
            raise ValueError('explicit single-memory deletion confirmation is required')
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            self.memory.check_revision(user_id, memory_id, expected_revision)
            deleted = self.memory.delete_one(user_id, memory_id,
                confirm_unattributed_audit_cleanup=confirm_unattributed_audit_cleanup, commit=False)
            self.graph.remove_memories([memory_id], commit=False)
        return deleted

    @synchronized
    def list_memories(self, user_id: str, *, memory_scope: str = DEFAULT_SCOPE):
        return self.memory.list(user_id, memory_scope=validate_memory_scope(memory_scope))

    @synchronized
    def memory_page(self, user_id: str, *, memory_scope: str = DEFAULT_SCOPE, before_id: int | None = None,
                    limit: int = 20) -> dict:
        return self.memory.page(user_id, memory_scope=memory_scope, before_id=before_id, limit=limit)

    @synchronized
    def list_memory_scopes(self, user_id: str):
        return self.memory.scopes(user_id)

    @synchronized
    def search_graph(self, query: str, user_id: str, *, memory_scope: str = DEFAULT_SCOPE):
        return self.graph.retrieve(query, user_id, memory_scope=memory_scope)

    @synchronized
    def close(self) -> None:
        self.graph.close()
        self.memory.close()
