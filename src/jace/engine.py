from __future__ import annotations

import os
import json
import re
import uuid
from contextlib import contextmanager
from functools import wraps
from threading import RLock
from pathlib import Path

from .canonical import CanonicalStore
from .wardrobe import INVENTORY_SOURCE, validate_inventory, encode_inventory, decode_inventory, build_wardrobe_plan
from .cleaning import PROFILE_SOURCE, validate_profile, encode_profile, decode_profile, build_plan
from .cognitive_graph import CognitiveGraph
from .ethics import assess
from .memory import MemoryStore, MemoryConflictError, validate_memory_revision
from .memory_scope import DEFAULT_SCOPE, validate_memory_scope
from .models import ActionProposal, ThoughtResult, utc_now
from .model_output import checked_text
from .evidence_output import OUTPUT_CONTRACT, render_selected_passages
from .practical import plan_for
from .reasoner import HttpJsonReasoner, LocalReasoner, Reasoner, configured_reasoner
from .syadvada import evaluate
from .temporal import recall_time, eligible_for_recall
from .context_review import (MAX_CONTEXT_BYTES, MAX_PREVIEW_BYTES, LIMITS as CONTEXT_LIMITS,
    bounded_payload, fingerprint, question, source_selection, memory_selection, selections, reasoner_descriptor, reasoner_snapshot)


class EngineBusyError(RuntimeError):
    """No engine operation was admitted; do not queue or retry it implicitly."""


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

    @contextmanager
    def request_admission(self):
        """Try one whole HTTP operation without changing direct-call semantics.

        The same reentrant lock protects nested calls, including think + learn.
        Admission is per engine instance and does not cancel admitted work.
        """
        if not self._lock.acquire(blocking=False):
            raise EngineBusyError('engine is busy; no engine work was started')
        try:
            yield
        finally:
            self._lock.release()

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
        evidence, memories, _ = self._retrieve_context(user_id, request, memory_scope)
        return self._answer_context(user_id, request, memory_scope, assessment, evidence, memories, self.reasoner)

    def _retrieve_context(self, user_id, request, memory_scope):
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
        return evidence, memories, context_time

    def _answer_context(self, user_id, request, memory_scope, assessment, evidence, memories, reasoner):
        perspectives = evaluate(request, [item.principle for item in evidence])
        try:
            response, action = reasoner.respond(request, assessment, perspectives, evidence, memories)
            checked_text(response, 'reasoner response', 32768, allow_crlf=True)
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
                checked_text(response, 'fallback response', 32768, allow_crlf=True)
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
    def preview_context(self, user_id: str, request: str, *, memory_scope: str = DEFAULT_SCOPE) -> dict:
        request, memory_scope, request_revision = question(user_id, request, memory_scope)
        assessment = assess(request)
        evidence, memories, at = [], [], recall_time()
        if assessment.allowed:
            # Snapshot all authoritative reads together, then release the read
            # transaction before any later model operation.
            with self.memory.connection:
                self.memory.connection.execute('BEGIN')
                evidence, memories, at = self._retrieve_context(user_id, request, memory_scope)
        context = {'canonical_evidence':[{'entry':item.to_dict(), 'revision':source_selection(item)['revision']} for item in evidence],
                   'memories':[item.to_dict() for item in memories]}
        bounded_payload(context, MAX_CONTEXT_BYTES, 'preview context')
        result = {'protocol':1, 'user_id':user_id, 'input':request, 'memory_scope':memory_scope,
                  'context_at':at, 'request_revision':request_revision,
                  'corpus_revision':fingerprint([item.to_dict() for item in self.canonical.all()]),
                  'blocked':not assessment.allowed, 'ethical_assessment':assessment.to_dict(),
                  'configured_reasoner':reasoner_descriptor(self.reasoner), 'limits':list(CONTEXT_LIMITS), **context}
        bounded_payload(result, MAX_PREVIEW_BYTES, 'context preview')
        return result

    @synchronized
    def answer_selected_context(self, user_id: str, request: str, *, sources, memories,
                                expected_request_revision: str, expected_corpus_revision: str,
                                confirm_context: bool = False, memory_scope: str = DEFAULT_SCOPE,
                                reasoner_mode: str = 'local', expected_reasoner_revision: str | None = None) -> dict:
        if confirm_context is not True:
            raise ValueError('explicit confirm_context=true is required before answering with selected context')
        request, memory_scope, request_revision = question(user_id, request, memory_scope)
        for value in (expected_request_revision, expected_corpus_revision):
            validate_memory_revision(value)
        if reasoner_mode not in ('local', 'configured', 'evidence_only'):
            raise ValueError('reasoner_mode must be local, configured or evidence_only')
        selected_sources, selected_memories = selections(sources, 'source'), selections(memories, 'memory')
        if reasoner_mode == 'evidence_only' and selected_memories:
            raise ValueError('evidence-only mode requires an empty memory selection')
        corpus = self.canonical.all()
        corpus_revision = fingerprint([item.to_dict() for item in corpus])
        if request_revision != expected_request_revision or corpus_revision != expected_corpus_revision:
            raise MemoryConflictError('Question, owner, scope or admitted corpus changed after review; preview again.')
        configured = self.reasoner
        descriptor, configuration = reasoner_snapshot(configured) if reasoner_mode == 'configured' else (None, None)
        if reasoner_mode == 'configured':
            validate_memory_revision(expected_reasoner_revision)
            if descriptor['kind'] == 'unavailable':
                raise ValueError('custom reasoners cannot be used in selected-context mode')
            if descriptor['revision'] != expected_reasoner_revision:
                raise MemoryConflictError('Configured reasoner destination changed after review; preview again.')
        elif expected_reasoner_revision is not None:
            raise ValueError('local and evidence-only modes must not include a configured-reasoner revision')
        assessment = assess(request)
        if not assessment.allowed:
            raise ValueError('This request cannot be answered through context review because the input harm gate rejected it.')
        by_id = {item.entry_id:item for item in corpus}
        evidence, captured = [], []
        for selected in selected_sources:
            entry = by_id.get(selected['entry_id'])
            if entry is None or source_selection(entry) != selected:
                raise MemoryConflictError('A selected source changed or is no longer admitted; preview again.')
            evidence.append(entry)
        at = recall_time()
        with self.memory.connection:
            self.memory.connection.execute('BEGIN')
            for selected in selected_memories:
                memory = self.memory.get_owned(user_id, selected['memory_id'])
                if memory.memory_scope != memory_scope:
                    raise LookupError('selected memory not found in this scope')
                if not eligible_for_recall(memory.expires_at, at) or memory_selection(memory) != selected:
                    raise MemoryConflictError('A selected memory changed or expired after review; preview again.')
                captured.append(memory)
        bounded_payload({'canonical_evidence':[item.to_dict() for item in evidence],
                         'memories':[item.to_dict() for item in captured]}, MAX_CONTEXT_BYTES, 'selected context')
        # No retrieval, graph supplement, learning or action execution here.
        # Freeze the reviewed HTTP destination/model/credential into an isolated
        # standard adapter. Later mutations to the configured instance cannot
        # redirect this already captured request or substitute its transport.
        if reasoner_mode == 'evidence_only':
            # Never enter the generative path, including its local fallback and
            # perspective construction. Failed display checks produce no output.
            response = render_selected_passages(evidence)
            if not assess(response).allowed:
                raise ValueError('Selected passages cannot be displayed because the output safety check rejected them.')
            result = ThoughtResult(
                request_id=str(uuid.uuid4()), user_id=user_id, input=request,
                response=response, ethical_assessment=assessment, perspectives=[],
                canonical_evidence=evidence, memories_used=[], action=None,
                created_at=utc_now(), memory_scope=memory_scope,
            ).to_dict()
        else:
            selected_reasoner = LocalReasoner()
            if reasoner_mode == 'configured' and descriptor['kind'] == 'http_json':
                url, api_key, model = configuration
                selected_reasoner = HttpJsonReasoner(url, api_key=api_key, model=model)
            result = self._answer_context(user_id, request, memory_scope, assessment, evidence, captured,
                                          selected_reasoner).to_dict()
        result['action'] = None
        result['context_review'] = {'protocol':1,'reasoner_mode':reasoner_mode,'request_revision':request_revision,
            'corpus_revision':corpus_revision,'sources':selected_sources,'memories':selected_memories,
            'selected_at':at,'configured_reasoner':descriptor}
        if reasoner_mode == 'evidence_only':
            result['context_review']['output_contract'] = OUTPUT_CONTRACT
        bounded_payload(result, MAX_PREVIEW_BYTES, 'selected-context answer')
        return result

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
            if self.memory.get_owned(user_id, memory_id).source in (PROFILE_SOURCE, INVENTORY_SOURCE):
                raise ValueError('Use the matching typed update operation; generic text correction cannot change a typed profile or inventory.')
            memory, notes = self.memory.replace(user_id, memory_id, content, commit=False)
            if memory:
                self.graph.remove_memories([memory_id], commit=False)
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def save_cleaning_profile(self, user_id: str, profile: dict, *, confirm_save: bool = False,
                              memory_scope: str = DEFAULT_SCOPE, expires_at: str | None = None):
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('user_id is required')
        if confirm_save is not True:
            raise ValueError('explicit confirm_save=true is required to persist a cleaning profile')
        validated = validate_profile(profile)
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            memory, notes = self.memory.add(user_id, encode_profile(validated), source=PROFILE_SOURCE,
                expires_at=expires_at, memory_scope=memory_scope, commit=False)
            if memory:
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def update_cleaning_profile(self, user_id: str, memory_id: int, profile: dict, *,
                                expected_revision: str, confirm_save: bool = False):
        self._validate_memory_identity(user_id, memory_id)
        if confirm_save is not True:
            raise ValueError('explicit confirm_save=true is required to replace a cleaning profile')
        validated = validate_profile(profile)
        validate_memory_revision(expected_revision)
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            self.memory.check_revision(user_id, memory_id, expected_revision)
            if self.memory.get_owned(user_id, memory_id).source != PROFILE_SOURCE:
                raise ValueError('only an existing typed cleaning profile can be updated here')
            memory, notes = self.memory.replace(user_id, memory_id, encode_profile(validated), commit=False)
            if memory:
                self.graph.remove_memories([memory_id], commit=False)
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def plan_cleaning(self, user_id: str, *, memory_scope: str = DEFAULT_SCOPE,
                      profile_memory_id: int | None = None, expected_profile_revision: str | None = None) -> dict:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('user_id is required')
        memory_scope = validate_memory_scope(memory_scope)
        if expected_profile_revision is not None:
            validate_memory_revision(expected_profile_revision)
            if profile_memory_id is None:
                raise ValueError('expected_profile_revision requires an explicit profile_memory_id')
        at = recall_time()
        if profile_memory_id is None:
            memories = self.memory.active_cleaning_profiles(user_id, memory_scope=memory_scope, at=at)
        else:
            self._validate_memory_identity(user_id, profile_memory_id)
            memory = self.memory.get_owned(user_id, profile_memory_id)
            if memory.memory_scope != memory_scope or memory.source != PROFILE_SOURCE or not eligible_for_recall(memory.expires_at, at):
                raise LookupError('an eligible cleaning profile was not found in this scope')
            # Compare the same immutable row snapshot that builds the checklist.
            if expected_profile_revision is not None and memory.revision != expected_profile_revision:
                raise MemoryConflictError('Profile changed after review. Reload before planning.')
            memories = [memory]
        # Validate every active candidate. Never guess past a malformed record
        # or silently select the newest of conflicting declarations.
        profiles = [decode_profile(memory) for memory in memories]
        common = {'user_id': user_id, 'memory_scope': memory_scope, 'context_at': at,
                  'actions_executed': False, 'action': None}
        if not memories:
            return {**common, 'status': 'needs_profile', 'steps': [],
                    'message': 'Create an explicit typed cleaning profile before planning. Free-form memories are not inferred into constraints.'}
        if len(memories) > 1:
            return {**common, 'status': 'choose_profile', 'steps': [],
                    'message': 'Several active profiles exist. Explicitly choose profile_memory_id; no profile has been applied.',
                    'profiles': [{'memory_id': memory.memory_id, 'revision': memory.revision, 'profile': profile.to_dict()}
                                 for memory, profile in zip(memories, profiles)]}
        plan = build_plan(profiles[0])
        evidence = self.canonical.search('ahimsa aparigraha resources gentle reversible cleaning', limit=5)
        return {**common, **plan, 'status': 'planned', 'profile_memory': memories[0].to_dict(),
                'canonical_evidence': [item.to_dict() for item in evidence],
                'grounding': LocalReasoner._grounding(evidence)}

    @synchronized
    def save_wardrobe_inventory(self, user_id: str, inventory: dict, *, confirm_save: bool = False,
                                memory_scope: str = DEFAULT_SCOPE, expires_at: str | None = None):
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('user_id is required')
        if confirm_save is not True:
            raise ValueError('explicit confirm_save=true is required to persist a wardrobe inventory')
        content = encode_inventory(inventory)
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            memory, notes = self.memory.add(user_id, content, source=INVENTORY_SOURCE,
                memory_scope=memory_scope, expires_at=expires_at, commit=False)
            if memory and memory.content != content:
                raise ValueError('Inventory labels were altered by the memory filter; use ordinary non-sensitive labels.')
            if memory:
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def update_wardrobe_inventory(self, user_id: str, memory_id: int, inventory: dict, *,
                                  expected_revision: str, confirm_save: bool = False):
        self._validate_memory_identity(user_id, memory_id)
        if confirm_save is not True:
            raise ValueError('explicit confirm_save=true is required to replace a wardrobe inventory')
        content = encode_inventory(inventory)
        validate_memory_revision(expected_revision)
        with self.memory.connection:
            self.memory.connection.execute('BEGIN IMMEDIATE')
            self.memory.check_revision(user_id, memory_id, expected_revision)
            if self.memory.get_owned(user_id, memory_id).source != INVENTORY_SOURCE:
                raise ValueError('only an existing typed wardrobe inventory can be updated here')
            memory, notes = self.memory.replace(user_id, memory_id, content, commit=False)
            if memory and memory.content != content:
                raise ValueError('Inventory labels were altered by the memory filter; use ordinary non-sensitive labels.')
            if memory:
                self.graph.remove_memories([memory_id], commit=False)
                self.graph.add_memory(memory, self.canonical.all(), commit=False)
        return memory, notes

    @synchronized
    def plan_wardrobe(self, user_id: str, *, memory_scope: str = DEFAULT_SCOPE,
                      inventory_memory_id: int | None = None, expected_inventory_revision: str | None = None,
                      include_derivation: bool = False) -> dict:
        if type(include_derivation) is not bool:
            raise ValueError('include_derivation must be an explicit boolean')
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError('user_id is required')
        memory_scope = validate_memory_scope(memory_scope)
        if expected_inventory_revision is not None:
            validate_memory_revision(expected_inventory_revision)
            if inventory_memory_id is None:
                raise ValueError('expected_inventory_revision requires an explicit inventory_memory_id')
        at = recall_time()
        if inventory_memory_id is None:
            memories = self.memory.active_typed_records(user_id, INVENTORY_SOURCE, memory_scope=memory_scope, at=at)
        else:
            self._validate_memory_identity(user_id, inventory_memory_id)
            memory = self.memory.get_owned(user_id, inventory_memory_id)
            if memory.memory_scope != memory_scope or memory.source != INVENTORY_SOURCE or not eligible_for_recall(memory.expires_at, at):
                raise LookupError('an eligible wardrobe inventory was not found in this scope')
            if expected_inventory_revision is not None and memory.revision != expected_inventory_revision:
                raise MemoryConflictError('Inventory changed after review. Reload before planning.')
            memories = [memory]
        inventories = [decode_inventory(memory) for memory in memories]
        common = {'user_id': user_id, 'memory_scope': memory_scope, 'context_at': at,
                  'actions_executed': False, 'action': None}
        if not memories:
            return {**common, 'status': 'needs_inventory', 'item_steps': [],
                    'message': 'Explicitly save a typed inventory before planning; free-form conversation is not interpreted.'}
        if len(memories) > 1:
            return {**common, 'status': 'choose_inventory', 'item_steps': [],
                    'message': 'Several active inventories exist. Explicitly select inventory_memory_id; no newest-wins assumption is made.',
                    'inventories': [{'memory_id': memory.memory_id, 'revision': memory.revision} for memory in memories]}
        plan = build_wardrobe_plan(inventories[0], include_derivation=include_derivation)
        evidence = self.canonical.search('aparigraha restraint resources reversible wardrobe', limit=5)
        result = {**common, **plan, 'status': 'planned', 'inventory_memory': memories[0].to_dict(),
                'canonical_evidence': [item.to_dict() for item in evidence], 'grounding': LocalReasoner._grounding(evidence)}
        if include_derivation:
            bounded_payload(result, 64 * 1024, 'explained wardrobe plan')
        return result

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
