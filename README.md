# JACE — Jain AI Cognitive Engine

JACE is a local-first reference implementation of the Jain AI Brain blueprint. It provides a runnable cognitive loop:

```text
input → ethical gate → iterative GraphRAG activation → unanswered reflection prompts → response/action proposal
```

The implementation is deliberately safe to run on a laptop. It does not pretend to be conscious, does not directly drive motors, and does not silently train on user data. Cloud model, vector database, voice, and ROS 2 integrations are explicit adapters.

The activation graph is the memory/neural-network enhancement: canonical principles are immutable nodes, aligned memories become dynamic nodes, and each query performs bounded seed → expand → rerank retrieval. This creates persistent associative structure without pretending that live user text has retrained model weights.

The seven reflection rows are [explicitly unevaluated](docs/REFLECTION_PROMPTS.md). They contain no numeric confidence and do not establish support, contradiction, truth or valid Jain doctrinal reasoning.

## Recent measured progress

- [Inspect approved private source material](docs/PRIVATE_SOURCE_STUDY.md): an explicit per-invocation CLI keeps source study separate from canonical reasoning, memory and providers. Source files are supplied privately; no corpus or learned model is bundled. This is literal lookup and fixed fragment retrieval, not Jain decision-making.
- [Run actual small CPU training](docs/CPU_EVIDENCE_ROUTER.md): real optimization and reload on original synthetic notes. Ranking improved on a small holdout, while accept/abstain decisions were worse than TF-IDF. This is not an Agama-trained language model.
- [Inspect bounded humanoid motion](docs/FREEBASE_GAIT_PROBE.md): an original contact-aware controller performs two measured alternating steps and recovers double support over eight seconds in the pinned simulation. Independent modest-push cases pass and a stronger push fails. This is not sustained walking, general balance or hardware qualification. The earlier [posture feedback](docs/FREEBASE_BALANCE.md) remains separate.
- [Use the local text prototype](docs/LOCAL_QUALIFICATION.md): installed-package smoke verified; real browser/audio and hosted deployment remain unqualified.

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
# If running directly from the checkout without installation:
# Windows cmd: set PYTHONPATH=src
# Linux/macOS: export PYTHONPATH=src
python -m jace.cli health
python -m jace.cli ask "How can I move through a crowded room?"
python -m jace.cli remember demo-user "The user prefers quiet spoken responses"
python -m jace.cli simulate
python -m jace.cli serve
```

The HTTP service listens on `http://127.0.0.1:8787`. The CLI remains usable without HTTP credentials. HTTP access other than `/health` is disabled until an operator configures `JACE_AUTH_TOKENS` in the process environment. This JSON object maps each existing bearer token to one user ID. Tokens must be at least 32 non-whitespace ASCII characters and should be cryptographically random. Do not put actual tokens in Git, command history, logs, or shared browser storage. This project does not generate, provision, or save credentials for you.

Clients send `Authorization: Bearer <assigned token>`. The token's user ID is authoritative; another `user_id` receives HTTP 403. Missing/invalid credentials receive 401, and an unconfigured service receives 503. `/health` is public but does not disclose memory or graph counts. Configure credentials through your deployment's authorized secret mechanism before using HTTP; use the CLI meanwhile.

The browser console accepts an assigned token in a password field and keeps it only in the current page. Its User value must match the token's user ID. CORS allows only `http://127.0.0.1:8080` and `http://localhost:8080` by default; set explicit origins with `JACE_ALLOWED_ORIGINS`. Never send bearer tokens over public plaintext HTTP. Public hosting still needs HTTPS, rate limiting, retention policies and an operator-reviewed authentication lifecycle.

Requests may contain at most one `Authorization` and one `Origin` header. Repeated names, including mixed casing and identical values, are rejected before route/engine work (normally 400; earlier size/rate checks can reject first). Ambiguous Origin values are not reflected in CORS headers. Token-map JSON rejects duplicate decoded keys, including escaped equivalents, instead of silently selecting the last owner. Well-formed singleton requests and unique-key configuration retain their behavior. Public health and valid preflight still need no bearer token; protected routes do. These synthetic raw-loopback checks do not establish a proxy exploit, tokenless-access defect or real-browser CORS qualification.

For a browser voice console, run `python -m http.server 8080 --bind 127.0.0.1 --directory web` in a second terminal and open `http://127.0.0.1:8080`. Speech recognition and playback depend on browser/device support; the text API remains usable when audio is unavailable. Dictation is never sent to JACE until you review the transcript and click Ask JACE.

```bash
curl -X POST http://127.0.0.1:8787/v1/think \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JACE_CLIENT_TOKEN" \
  -d '{"user_id":"demo-user","input":"How should I approach a fragile object?"}'
```

## Endpoints

- `GET /health` — runtime and adapter status.
- `POST /v1/think` — analyse a request and return a response, seven unanswered reflection prompts, evidence, and any proposed action.
- `POST /v1/think` with `"learn": true` — additionally persist only explicit preference/fact statements from that turn.
- `POST /v1/memory` — add a user memory only after the Pratikramana alignment filter; optional `expires_at` controls future recall.
- `PATCH /v1/memory` with `memory_id` and `content` — explicitly correct an owned memory after the alignment filter; memory and graph update atomically. Other users' memory IDs return 404.
- `PATCH /v1/memory-expiration` with `memory_id` and `expires_at` — explicitly set an owned memory's recall expiry, or use `null` to remove expiry.
- `GET /v1/memory/<user_id>?memory_scope=home` — inspect that owner's stored memories in the chosen scope (default: `default`).
- `GET /v1/memory-scopes` — list the authenticated owner's named memory scopes.
- `GET /v1/memory-item/<memory_id>` — preview deletion of one owned memory and any legacy audit cleanup warning.
- `DELETE /v1/memory-item/<memory_id>` — explicitly confirmed deletion of one owned item; any unattributed audit cleanup requires a separate choice.
- `DELETE /v1/memory/<user_id>` — explicitly confirmed deletion of all that owner's memory scopes, graph nodes/edges and audit records, including expired memories. Requires the separate whole-owner confirmation described below. This is logical deletion from the live database, not a guarantee of erasure from backups, SQLite storage remnants or an external model provider.
- `GET /v1/canonical/search?q=...` — search immutable canonical principles.
- `GET /v1/graph/search?q=...&user_id=...` — inspect activated GraphRAG nodes and scores.
- `POST /v1/simulate/motion` — run a hardware-free safety decision against a sensor observation.

Whole-owner deletion requires exactly one `X-JACE-Confirm-Owner-Delete` header with value `all-memories-graph-and-audit:<percent-encoded authenticated owner>`, for example `all-memories-graph-and-audit:alice`. Encode the exact owner as UTF-8 with Python `urllib.parse.quote(owner, safe='')`, not form encoding; case and percent escapes must match. Missing, wrong or duplicate assertions return 409 before engine work. This intentionally breaks older whole-owner HTTP calls: clients must collect an explicit all-scope deletion choice, not automatically copy the error's required header and retry. See [deletion contract and limits](docs/MEMORY_DELETION.md).

The route requires an owner path with no query, path parameters or fragment; absolute-form URLs are also rejected. A scoped list URL such as `/v1/memory/alice?memory_scope=work` is rejected for deletion rather than silently deleting other scopes. The single-item headers `X-JACE-Confirm-Delete`, `X-JACE-Confirm-Audit-Cleanup` and `X-JACE-If-Memory-Revision` are also rejected on this whole-owner route, even if empty; use `/v1/memory-item/<memory_id>` for those conditions. The new header is a caller assertion of purpose and owner, not proof of human consent, a fresh review or replay protection. It does not add scoped bulk deletion, change direct engine/CLI behavior or replace standard-library URL parsing and leading-slash normalization. Existing browser and CLI tools delete individual items only; they do not add this header automatically.

## Project layout

- `src/jace/ethics.py` — Ahimsa, Aparigraha, and safety policy checks.
- `src/jace/syadvada.py` — fixed, unanswered reflection prompts with legacy sevenfold labels.
- `src/jace/canonical.py` — read-only canonical knowledge store.
- `src/jace/corpus.py` — provenance-aware reviewed-text ingestion.
- `src/jace/cognitive_graph.py` — persistent activation graph and iterative GraphRAG loop.
- `src/jace/simulator.py` — conservative motion decisions for simulator testing.
- `src/jace/physics.py` — optional real MuJoCo closed-loop slider fixture; no hardware.
- `src/jace/articulated.py` and `src/jace/reaching.py` — original fixed-base articulated physics and bounded planar hand-target planning; no gait or hardware.
- `src/jace/memory.py` — SQLite continuous memory with sanitisation and audit trail.
- `src/jace/reasoner.py` — local deterministic reasoner plus an optional structured HTTP model adapter.
- `src/jace/model_output.py` — mechanical source-ID/exact-excerpt checks, not semantic grounding.
- `src/jace/engine.py` — orchestration of the complete cognitive loop.
- `src/jace/api.py` — standard-library HTTP API.
- `integrations/` — optional voice and ROS 2 boundaries; hardware is never enabled by default.
- `web/index.html` — dependency-free browser voice console using the Web Speech API.
- `scripts/train_qlora.py` — explicit offline synthetic-only training preflight and bounded run interface; real backend execution remains unverified.
- `scripts/ingest_corpus.py` — convert reviewed text files into canonical records.
- `scripts/evaluate.py` — run checked-in safety regression cases.

## Design boundaries

The canonical store is read-only at runtime and contains principles and references rather than an unverified claim to reproduce all Agama texts. User memory is separate, user-scoped, removable, and filtered before persistence. HTTP identity is bound to the configured bearer token; an arbitrary user ID is not authorization. New audit events do not duplicate memory text, and forgetting a user also removes their historical audit records. The built-in reasoner is a deterministic fallback; production deployments can implement `Reasoner` with a locally hosted or remote model while retaining the ethical gate and output schema.

### Continuous GraphRAG loop

1. A conversation is checked by the Ahimsa/Pratikramana gate.
2. Only an accepted, sanitised memory is written to SQLite and added as a dynamic graph node.
3. Shared terms create weighted `aligned_with` edges to canonical principles; canonical nodes and edges cannot be changed by dialogue.
4. A later query activates matching seeds, expands through related principles and memories for at most two hops, and reranks the result.
5. The reasoner receives only selected context. No automatic model-weight training occurs in production; the separate `scripts/train_qlora.py` interface currently admits only explicitly reviewed synthetic fixtures and requires explicit run consent.

### Corpus ingestion

The repository includes a small principles file for the MVP, not a claim to contain the complete Agamas. Add only reviewed and legally usable source text:

```bash
python scripts/ingest_corpus.py texts/tattvartha.txt \
  --output data/corpus.json \
  --work "Tattvartha Sutra" \
  --source "Edition, translator, page or URL" \
  --language en --license "record the applicable licence" \
  --tag ahimsa --tag anekantavada --verified
```

Runtime ingestion requires `--verified` and a recorded `--license`; these are human declarations, not an automated legal or scholarly validation. Use `--draft` for review-only output with `verified: false`, which cannot be loaded as an external runtime corpus. `--draft` and `--verified` are mutually exclusive, including in the library API; conflicting or non-boolean mode declarations are rejected before reading inputs or changing output. Complete the separate rights and content review before making a new runtime-mode export. External records must include work, source, location, language, license and `verified: true`. The built-in six-record fallback remains clearly labeled sample principles.

Every generated chunk contains a hash stable across checkout paths, work, edition/source, location, language, licence, and review flag. A generated paraphrase is labelled as interpretation and is not presented as a quotation.

Legacy list records support record-only excerpt matching: the older ingester normalizes whitespace and does not preserve a checked link to original file bytes. For newly prepared reviewed UTF-8 sources, `scripts/build_source_bundle.py` can instead create an explicit-consent private bundle with SHA-256 and exact byte spans. Runtime citations identify which level was checked. Rights and review remain human declarations; no real religious corpus has been qualified by this work. See [exact-source format, safe local build, limits and compatibility changes](docs/SOURCE_INTEGRITY.md).

Before preparing external sources, run `python -m jace.cli source-capabilities` for a read-only platform check. Native Windows exact-source IO is not implemented; unsupported operations fail before source reads or staging. Available prerequisites are not a filesystem qualification. See [platform limits and Windows requirements](docs/SOURCE_PLATFORMS.md).

For an authorized local runtime, `JACE_CANONICAL_PATH` can identify a bounded legacy JSON list or the new bundle's `bundle.json`. Building a bundle does not activate it or authorize provider transmission, sharing or training.

For material whose copying/review is permitted but whose passages still need review, the [offline source-review workflow](docs/SOURCE_REVIEW.md) prepares a runtime-rejected draft and private local review screen. Per-passage decisions bind the exact text, spans and metadata before a separately confirmed export. A saved report can be explicitly reloaded into its exact draft to resume review, without restoring save or export consent. Only approved records are admitted, but complete backing files, including unapproved spans, are retained. Review and rights remain declarations, not verified scholarship or legal clearance.

### Container and checks

The container recipe is an unqualified local API starting point, not a public
deployment. Compose publishes only on host loopback (`127.0.0.1:8787`); the
container still listens on its internal interfaces for that mapping. Docker
networking must be checked on the selected host before relying on this boundary.
The build context allowlist excludes runtime databases and research files.
Only the six packaged sample principles are included, and HTTP routes other
than health remain locked without separately authorized credentials. See
[local deployment prerequisites and limits](docs/LOCAL_QUALIFICATION.md).

```bash
docker compose up --build
```

Stop with Ctrl-C or `docker compose stop`. The `jace-data` volume persists;
stopping containers does not erase conversations or audit records. Do not use
real personal data for a smoke test. Docker startup, shutdown and networking
have not been executed in the current qualification environment.

The checks below are runnable locally. This branch does not contain a GitHub Actions workflow, and no remote CI result is claimed. Any future CI configuration must be introduced on `main` under the repository owner's main-only workflow policy; feature branches must not contain or trigger workflows.

Run checks with:

```bash
python scripts/evaluate.py
python -m unittest discover -s tests -v
```

## Current implementation limits

This is an early local reference prototype, not the complete research vision. It contains six sample principles, a lexical graph and a deterministic fallback. It does not include the complete Agamas, a trained model, a working QLoRA trainer, real-time duplex voice, a free-base humanoid controller or a verified public deployment. The optional HTTP adapter sends the request and selected context to the operator's configured endpoint; obtain appropriate consent and review provider retention before enabling it.

The policy gate is a first-pass English pattern filter. Rejected inputs are stopped before any model call, and generated text is checked with the same limited filter, but neither mechanism proves harmlessness or Jain correctness. Missing or invalid simulator sensor values produce a stop proposal. No simulator decision is executable motor control.

See [implementation status](docs/IMPLEMENTATION_STATUS.md) for the remaining delivery gates.

### Explicit memory corrections and consent

Browser chat does not save conversations by default. Check “Remember an explicit preference or fact from this message” only when you want the current message considered for storage. The same narrow learning filter applies to text and spoken messages; this is not automatic extraction of every conversation.

Use `PATCH /v1/memory` with your bearer token and a JSON body containing `memory_id` and `content` to replace a mistaken preference. The CLI equivalent is `python -m jace.cli correct-memory USER_ID MEMORY_ID "corrected preference"`. A correction preserves the memory ID and creation time, records an update time, and replaces graph content in one transaction. Rejected corrections leave the prior memory intact. This supports explicit correction, not automatic resolution of every contradictory statement.

### Corpus version isolation

Each graph instance retrieves only canonical nodes from the exact admitted corpus content loaded at startup. Content-addressed namespaces prevent a changed or removed record, an older unreviewed sample, or another engine using the same database from silently entering that instance's canonical results. Prior corpus nodes stay on disk for non-destructive compatibility, so graph statistics can include historical nodes. Private memories remain user-scoped and are not erased when a corpus changes.

Browser learning consent applies to one submitted message. The checkbox is consumed before the request starts, including when the request fails; a later message requires a new choice.

### Unicode lexical retrieval

Canonical, memory and graph search preserve combining marks in Hindi/Gujarati and normalize equivalent Unicode spellings. Retrieval matches words rather than arbitrary substrings. This is same-language lexical matching, not translation or multilingual semantic reasoning; the built-in six sample principles remain English, and automatic memory phrase detection remains English-only.

### Bounded practical-answer fallback

Without a model, three authored scenario plans now cover the brief's household-cleaning, wardrobe-organization and business-partner-dispute examples. They provide distinct steps, trade-offs and a clarifying question, and propose no physical action. Recognized compound requests and known software/negation cases receive a transparent generic fallback. Topic detection is lexical, so other false positives and missed requests remain possible; it does not understand intent or arbitrary negation. These templates are not trained reasoning or expert advice.

Responses separate practical suggestions from retrieved passages. Built-in samples never count as reviewed Agama citations. External source references copy only admitted record IDs, work/source/location metadata and passage text; declared review/licensing still requires human verification. The templates do not interpret or reconcile private memory preferences.

The offline evaluation script forces the local fallback and built-in fixture even when model/corpus environment variables are set. Its eight checked-in cases are regressions, not a scholarly or model-quality benchmark.

### Sanskrit query preparation

The separate [query-preview helper](docs/PREPARE_SANSKRIT_QUERY.md) converts explicitly declared Sanskrit fragments from Devanagari or Gujarati script to Latin IAST for human review. It opens no sources and does not translate Hindi/Gujarati questions or run a search. Existing source-study opt-ins remain required.

### Hindi and Gujarati local text

The local fallback has authored Hindi/Gujarati versions of its three existing practical plans, plus abstention, refusal and source-limit messages. Type native-script questions such as `घर की सफाई कैसे करूँ?` or `વ્યવસાયના ભાગીદાર સાથે મતભેદ કેવી રીતે ઉકેલું?`. Exact source passages stay in their original language. This is bounded script/keyword routing, not translation, general multilingual reasoning, Agama training or verified audio. See [examples and limits](docs/HINDI_GUJARATI_LOCAL.md).

### Local HTTP service bounds

The local server admits at most 16 simultaneous connections by default and returns 503 when full. Headers and bodies must finish within one absolute 10-second read deadline, including slow byte-by-byte sends. Targets are limited to 8 KiB, headers to 16 KiB after standard-library parsing, and JSON bodies to 64 KiB. Ambiguous Content-Length and Transfer-Encoding framing are rejected. Each connection handles one request and closes.

A bounded in-process token bucket allows a burst of 30 requests per peer address and replenishes 60 per minute by default, including health and preflight requests. Excess requests receive 429 with Retry-After. Accounting tracks at most 1,024 addresses; only fully replenished idle records expire. Forwarded-address headers are deliberately ignored, so users behind a proxy/NAT share its limit. See .env.example for finite positive limits.

The read deadline ends before application work. Engine-backed HTTP routes now use [nonqueued engine admission](docs/ENGINE_ADMISSION.md): after authorization and request reads, a busy engine returns a distinct 503 before starting that operation. One admission spans thinking and any explicitly requested learning. Public health checks bypass the engine lock but remain subject to connection/rate limits. Already admitted work can still finish after a disconnect; direct in-process calls retain blocking behavior. Shutdown waits for admitted handlers. These local bounds are not production readiness: TLS, a hardened deployment server, distributed abuse controls, operator-managed token rotation/revocation, monitoring and reviewed capacity limits remain necessary.

### Voice turn controls and verification limits

The browser adapter offers English (`en-IN`), Hindi (`hi-IN`) and Gujarati (`gu-IN`) recognition preferences. It asks the user to review the transcript before submission, requires per-message learning consent, ignores superseded responses, and cancels playback/listening on request or connection changes. Read-aloud is opt-in and uses an available matching voice. Selecting a voice language does not translate text or make the English template/ethics engine multilingual.

Stop/cancel affects this page, not work already accepted by the server. An opted-in memory may already have been saved before cancellation. Requests are not automatically retried. Changing account/token/API fields clears the previous draft and response and invalidates pending callbacks. Changing the user or API destination also clears the previous token, requiring the assigned token again. Tokens are still kept only in page memory. Playback requests abort of active dictation and waits for the browser's recognition-ended event before speaking. If that event never arrives, playback remains blocked and can be cancelled. Actual microphone shutdown timing still requires real-device verification.

Browser speech recognition has [limited support and can send audio to a browser-provider web service](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition). Language tags select a [recognition preference](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/lang), not a guarantee of availability. Playback uses the [voices actually available on the current device](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/getVoices).

The conversation adapter binds retained drafts, replies, dictation and one-message learning consent to exact owner/token/API/scope fields. Learning requires a new checkbox-change event tied to the raw message, consumed before validation or network work. Silent identity/message changes are checked before actions and across response reads; pending requests and stale transcripts/playback are discarded. Page exit and restoration clear credentials, private text and learning/read-aloud choices. Only trusted HTTPS or literal loopback/localhost HTTP origins are accepted; redirects and cookies are disabled, JSON responses are capped at 1 MiB, and replies must echo the sent owner/question/scope. An already submitted request may still finish, call its configured reasoner or save an opted-in memory; cancellation never recalls it or retries automatically. There is no absolute browser fetch deadline.

The Node-based script harness covers transcript review, repeated/interrupted/denied recognition, consent, cancellation, stale responses, account changes and voice selection. Additional synthetic regressions cover silent identity/draft drift, learning snapshots, reset paths, stream cancellation, restored state, origin validation and mismatched replies. Two Node-to-Python loopback cases use synthetic credentials and the explicit local template reasoner to check scoped one-use learning and owner rejection. It does not verify a real microphone, pronunciation, real browser media behavior, recognition accuracy or latency. These state checks do not protect against malicious scripts/extensions, detect silent changes restored between observations or guarantee immediate idle-page erasure. Browser autofill, restoration, layout, accessibility and real cookie/redirect enforcement remain unqualified by script fixtures. No audio recording was made during these tests. Full-duplex transport, actual STT/TTS models, VAD/barge-in and multilingual reasoning remain separate work.

### Optional real physics integration

A CPU-only MuJoCo adapter now runs an original one-axis slider scene through geometry-derived observations, bounded simulated actuation and measured contacts. Six fixtures cover clear/blocked paths, a tagged living obstacle, intrusion, sensor loss and uncertainty. Motion requires explicit simulation-only opt-in. See [the simulation setup, evidence and limits](docs/SIMULATION.md). This is actual physics stepping, but not humanoid simulation, vision, walking, routing or hardware control.

### Fixed-base articulation step

An original nine-hinge humanoid-shaped fixture now exercises a slow shoulder/elbow posture transition under real MuJoCo dynamics and gravity. It has simulation-only consent, bounded actuators, latched holding on uncertainty, whole-model obstacle clearance checks and explicit contact/failure reporting. [Articulation setup and adversarial evidence](docs/ARTICULATION.md) distinguish six bounded cases from an intentionally unavoidable overlap. Its pelvis is fixed: this is not walking, standing balance, perception or real hardware qualification.

### Bounded hand-target simulation

The optional MuJoCo fixture can now solve a left-hand world-coordinate goal, verify its kinematics, and execute a confirmed simulation through the existing stop controller. Use `python -m jace.cli simulate-reach --target 0.3793621956 0.22 1.0707036952 --plan-only` to preview, then replace `--plan-only` with `--confirm-simulation` to run. Reports measure actual endpoint error and distinguish reach, hold, short horizon and contact failure. This is two-joint planar control on a fixed-base model, not walking, perception, grasping or hardware control. See [the articulated fixture](docs/ARTICULATION.md#cartesian-hand-targets).

### Free-base diagnostic, not walking

A separately licensed, explicitly modified G1 model now exercises a true free root and 29 joints in a capped subprocess. Its source neutral servos lose upright posture after about 1.02 simulated seconds; the diagnostic records that failure instead of claiming standing or gait. It loads no pretrained policy and exposes no hardware bridge. See [source, BSD notices, limits and expected failures](docs/FREEBASE_DIAGNOSTIC.md).

### Forget a single memory

Use `python -m jace.cli memories USER` to review recent IDs, then `python -m jace.cli forget-memory USER ID` for a non-destructive preview. Deletion requires `--confirm-delete`. If unattributed audit entries exist, a separate explicit choice is required before removing all such entries for that owner; other active memories and attributable audits stay intact. See [confirmation, API and deletion limits](docs/MEMORY_DELETION.md).

### Temporary memories

Use `remember USER "temporary preference" --expires-at 2026-12-01T18:00:00Z` or `set-memory-expiration USER ID --at TIMESTAMP` to stop future recall at an explicit time. Both direct and graph retrieval exclude expired records; review and deletion remain available. `--never` explicitly removes expiry. Corrections preserve expiry, and dates are never inferred from conversation. See [time boundaries, API and retention limits](docs/MEMORY_EXPIRATION.md).

### Offline training preparation

The old print-only trainer is replaced by a bounded, explicit-consent implementation with synthetic train/held-out admission, local safetensors restrictions, resource caps, diagnostic evaluation and adapter-only export. Default invocation performs preflight only. No GPU/model training has been validated, and no collected texts or private memories are admitted. See [requirements, evidence and unverified backend limits](docs/OFFLINE_TRAINING.md).

### Model response checks

The optional HTTP adapter now requires a bounded JSON answer/citations contract. Cited IDs and exact excerpts must match reviewed records retrieved for that request; source metadata is rendered locally and generated prose remains explicitly unverified. Redirects and public plaintext endpoints are rejected, provider refusals remain refusals, and malformed outputs fall back locally. A [separate bounded transport worker](docs/MODEL_TRANSPORT.md) now ends a stalled or trickling request locally without retrying it; this cannot cancel provider work already accepted or revoke transmitted context. See [contract, privacy and unverified safety/provider limits](docs/MODEL_OUTPUT_BOUNDARY.md).

### Separate memory contexts

Use `--memory-scope home` or `--memory-scope work` with remembering, asking and memory review to keep unrelated contexts separate. HTTP requests and the conversation console expose the same selector. Existing records stay in `default`; no scope is inferred and no implicit union is performed. Scopes do not restrict another client holding the same owner token. See [migration, API, console compatibility and ownership limits](docs/MEMORY_SCOPES.md).

### Retrieval regression checks

Direct lexical recall now considers older owned memories within explicit work budgets, preserves direct-match ranking and supplements it with owner/scope/expiry-checked graph results. The original fictional benchmark measures selection and isolation, not model or scholarly quality. See [retrieval behavior, limits and measured baseline](docs/RETRIEVAL_RELIABILITY.md), and run `python scripts/evaluate_retrieval.py`.

### Review and manage saved memories

The conversation console links to `web/memory.html` for paged owner/scope review, explicit correction and expiry changes, and individually confirmed deletion. The new screen uses atomic record-state conditions to reject stale edits and separate consent for broader legacy-audit cleanup. See the [memory-manager guide and verification limits](docs/MEMORY_MANAGER.md). This client uses the existing API; it does not train a model or automatically extract new memories.

### Apply explicit cleaning preferences

`jace save-cleaning-profile` previews four typed choices and saves them only with `--confirm-save`; `jace plan-cleaning` reuses an eligible owned profile to build a local conditional checklist. Water, time and supply choices change the steps. Conflicting active profiles require explicit selection. See the [cleaning-profile workflow and limitations](docs/CLEANING_PROFILES.md). This dedicated path does not infer preferences from chat, call a model or perform actions.

The [explicit cleaning-planner screen](docs/CLEANING_PLANNER_SCREEN.md) now supports confirmed profile creation, review, revision-checked edits and checklist generation from saved choices. It is linked from the conversation console. Real loopback client tests exercise the flow; real browser behavior remains unverified.

### Review an explicit wardrobe inventory

The [wardrobe planner](docs/WARDROBE_PLANNER.md) takes explicitly confirmed item quantities, condition/fit/use/ownership/preservation choices and category minimums. It produces conditional item-specific reuse/repair/uncertainty checks and bounded possible-surplus review, without donation, disposal, purchases or model calls. Counts are declarations, not measured savings or an optimized wardrobe. The dedicated screen is linked from the conversation console.

### Review context before an answer

The separate `web/context.html` flow previews available sources and scoped private memories without a model call. All candidates start unchecked; one explicit confirmation selects the exact context for a local answer, or a separately chosen configured reasoner. The server rechecks ownership, expiry and source/memory/configuration revisions and adds no hidden retrieval results. Existing ordinary chat is unchanged. See [API, CLI, privacy boundaries and test evidence](docs/CONTEXT_REVIEW.md). This is selection control, not semantic verification or a trained reasoning system.


### Prepare an explicit partner discussion

The [stateless dispute worksheet](docs/DISPUTE_PREPARATION.md) compares two to four explicitly entered options against your reported positions, unknowns and constraints. It preserves disputed claims and reported agreement as declarations, asks option-specific review questions, and makes no verdict or recommendation. Use `jace prepare-dispute --stdin` or authenticated `POST /v1/plans/dispute`. No case data is saved, retrieved from memory, sent to a model or sent to a partner. The [dedicated review screen](docs/DISPUTE_SCREEN.md) is linked from the console, with a local preview and one-use confirmation before transmission. Script and loopback tests pass; real browser behavior remains unverified.
