# JACE — Jain AI Cognitive Engine

JACE is a local-first reference implementation of the Jain AI Brain blueprint. It provides a runnable cognitive loop:

```text
input → ethical gate → iterative GraphRAG activation → sevenfold Syādvāda analysis → response/action proposal
```

The implementation is deliberately safe to run on a laptop. It does not pretend to be conscious, does not directly drive motors, and does not silently train on user data. Cloud model, vector database, voice, and ROS 2 integrations are explicit adapters.

The activation graph is the memory/neural-network enhancement: canonical principles are immutable nodes, aligned memories become dynamic nodes, and each query performs bounded seed → expand → rerank retrieval. This creates persistent associative structure without pretending that live user text has retrained model weights.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m jace.cli health
python -m jace.cli ask "How can I move through a crowded room?"
python -m jace.cli remember demo-user "The user prefers quiet spoken responses"
python -m jace.cli serve
```

The HTTP service listens on `http://127.0.0.1:8787`.

```bash
curl -X POST http://127.0.0.1:8787/v1/think \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo-user","input":"How should I approach a fragile object?"}'
```

## Endpoints

- `GET /health` — runtime and adapter status.
- `POST /v1/think` — analyse a request and return a response, seven perspectives, evidence, and any proposed action.
- `POST /v1/think` with `"learn": true` — additionally persist only explicit preference/fact statements from that turn.
- `POST /v1/memory` — add a user memory only after the Pratikramana alignment filter.
- `GET /v1/memory/<user_id>` — inspect that user's stored memories.
- `GET /v1/canonical/search?q=...` — search immutable canonical principles.

## Project layout

- `src/jace/ethics.py` — Ahimsa, Aparigraha, and safety policy checks.
- `src/jace/syadvada.py` — deterministic sevenfold perspective evaluator.
- `src/jace/canonical.py` — read-only canonical knowledge store.
- `src/jace/cognitive_graph.py` — persistent activation graph and iterative GraphRAG loop.
- `src/jace/memory.py` — SQLite continuous memory with sanitisation and audit trail.
- `src/jace/reasoner.py` — local deterministic reasoner plus an optional HTTP LLM adapter.
- `src/jace/engine.py` — orchestration of the complete cognitive loop.
- `src/jace/api.py` — standard-library HTTP API.
- `integrations/` — optional voice and ROS 2 boundaries; hardware is never enabled by default.
- `scripts/train_qlora.py` — guarded Unsloth/QLoRA training entry point.

## Design boundaries

The canonical store is read-only at runtime and contains principles and references rather than an unverified claim to reproduce all Agama texts. User memory is separate, user-scoped, removable, and filtered before persistence. The built-in reasoner is a deterministic fallback; production deployments can implement `Reasoner` with a locally hosted or remote model while retaining the ethical gate and output schema.

### Continuous GraphRAG loop

1. A conversation is checked by the Ahimsa/Pratikramana gate.
2. Only an accepted, sanitised memory is written to SQLite and added as a dynamic graph node.
3. Shared terms create weighted `aligned_with` edges to canonical principles; canonical nodes and edges cannot be changed by dialogue.
4. A later query activates matching seeds, expands through related principles and memories for at most two hops, and reranks the result.
5. The reasoner receives only selected context. No automatic model-weight training occurs in production; reviewed datasets can be used by `scripts/train_qlora.py`.

Run checks with:

```bash
python -m unittest discover -s tests -v
```
