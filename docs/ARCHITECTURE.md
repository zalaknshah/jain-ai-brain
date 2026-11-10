# JACE architecture and delivery path

## Implemented vertical slice

```text
HTTP / CLI / voice adapter
        ↓
Ahimsa + Aparigraha policy gate
        ↓
SQLite memory + immutable canonical store
        ↓
bounded cognitive graph: seed → expand → rerank
        ↓
seven unanswered editorial reflection prompts
        ↓
local reasoner or optional OpenAI-compatible model
        ↓
text response + confirmation-gated action proposal
```

The system separates three kinds of information:

| Store | Mutable? | Purpose |
| --- | --- | --- |
| `data/canonical.json` | No at runtime | Unverified sample principles by default; external sources require review declarations |
| `memories` SQLite table | Yes, user-scoped | Preferences, environmental facts, and approved conversation memories |
| `graph_nodes` / `graph_edges` | Dynamic nodes only | Associative activation between memories and canonical principles |

## Reflection scaffold, not semantic evaluation

The legacy perspective fields now carry explicitly unevaluated reflection questions and null confidence. Neither input wording nor retrieved passage presence establishes a conclusion. Labels and row count are compatibility identifiers, not a qualified formalization of Jain doctrine. See [the output contract and migration](REFLECTION_PROMPTS.md). This correction does not implement entailment, contradiction detection or calibrated uncertainty.

## Iterative GraphRAG loop

The current no-dependency implementation provides an explainable local GraphRAG loop:

1. Tokenise the query and score matching canonical or user-memory nodes.
2. Activate matching seed nodes.
3. Traverse typed edges for at most two hops with a decay factor.
4. Rerank by activation score, hop depth, and stable node ID.
5. Send only the selected canonical evidence and memories to the reasoner.

This is the right interpretation of a “neural network of the brain” for the first product version: a persistent associative activation network. It is not a trained neural network and does not imply consciousness. A production deployment can replace lexical matching with embeddings, Qdrant, Neo4j, or Kùzu behind the same retrieval boundary.

## Canonical corpus ingestion

The repository intentionally does not claim to contain all Jain Agamas. Add source texts only when provenance, translation, copyright, language, and scholarly review are recorded. Each canonical record should contain:

```json
{
  "entry_id": "agama:source:chapter:paragraph",
  "title": "Source title",
  "principle": "A reviewed paraphrase",
  "guidance": "Application guidance clearly marked as interpretation",
  "source": "Edition, translator, page or URL",
  "tags": ["ahimsa", "anekantavada"]
}
```

Do not train or retrieve an unverified generated summary as if it were a canonical quote. Keep the original passage and translation metadata alongside any derived record.

## Continuous learning policy

Runtime learning is memory formation, not live weight training:

1. A user or application submits an explicit memory.
2. The Pratikramana filter rejects recognized direct harmful instructions and redacts likely credentials. It remains an English pattern filter, not a semantic safety guarantee.
3. Accepted content is scoped to the user and written to the audit-backed SQLite store.
4. The graph links the memory to related canonical principles.
5. Authorized users can inspect or delete their memories. New audit rows omit content; deletion also removes historical audit rows and associated graph nodes/edges. Backup and storage-remnant erasure is a separate operator responsibility.

Fine-tuning is a separate, reviewed offline process. Never feed raw private conversations directly into QLoRA training.

## Voice and robot boundaries

`integrations/voice_pipeline.py` accepts any STT function and passes text into JACE, so Faster-Whisper, Silero VAD, Pipecat, LiveKit, Kokoro, or Piper can be added without coupling them to the policy core. `integrations/ros2_bridge.py` rejects unconfirmed or unsafe action payloads. The bridge is a high-level safety boundary, not a substitute for ROS 2 controller limits, collision checking, emergency stop hardware, or simulation validation.

## Production progression

1. Replace the sample canonical records with reviewed, licensed corpus records using `scripts/ingest_corpus.py`.
2. Add multilingual source and response metadata for English, Hindi, and Gujarati.
3. Add embedding retrieval and graph entity extraction behind `CognitiveGraph`.
4. Run an adversarial evaluation set covering harm, privacy, bias, uncertainty, and action proposals.
5. Add Pipecat/LiveKit transport and Faster-Whisper/Kokoro only after the text API is stable.
6. Connect the ROS 2 bridge to MuJoCo/Webots/Isaac Sim with a simulator-only allowlist.
7. Host the API or UI on a free tier only after rate limits, authentication, secret management, and a data-retention policy are configured.

## Simulator contract

`jace simulate` and `POST /v1/simulate/motion` exercise the same high-level motion policy without requiring Isaac Sim, MuJoCo, Webots, ROS 2, or a GPU. Missing, malformed or non-finite sensor data produces a stop proposal. A living entity, fragile object, close obstacle, or uncertain sensor result produces `HALT_AND_REROUTE`; a clear path produces only a slow, confirmation-gated proposal. The result is intentionally not executable motor control. The optional `simulate-physics` CLI separately exercises actual MuJoCo stepping in an original one-axis fixture; see `docs/SIMULATION.md` for its explicit simulation confirmation, measured clearances and remaining limitations.

## Deployment

The root `Dockerfile` runs the standard-library HTTP service and `docker-compose.yml` persists the SQLite data volume. This is suitable for a small private deployment or as the basis of a Hugging Face Space. HTTP requests now require operator-configured bearer tokens bound to individual user IDs, except for a minimal public health endpoint. No credentials are created automatically. Public hosting still needs request limits, HTTPS, an audited credential lifecycle, secret management and an explicit memory-retention policy before exposing it to users.
