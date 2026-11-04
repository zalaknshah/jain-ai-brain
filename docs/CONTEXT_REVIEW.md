# Review context before answering

The new context-review flow lets a person inspect retrieved source passages and private memories, choose which records to use, and explicitly request an answer from that selection. It works for arbitrary questions rather than a scenario-specific profile. It does not implement semantic reasoning, infer that selected passages support an answer, or prove that a person actually reviewed them.

The existing voice/conversation console and `/v1/think` keep their previous behavior. Merely previewing context does not authorize those other routes, configure a provider, or add a standing data-sharing permission. Use the separate `web/context.html` screen or the endpoints below for this reviewed-selection contract.

## What the screen does

1. Enter the trusted API, assigned account/token, explicit memory scope and question. Preview sends these to the JACE API for local retrieval, not to a model provider. It does not save a memory or execute an action.
2. Review the full candidate passages, source declarations and optional byte-integrity references, plus the complete owned memory records and their expiration times. Every selection checkbox starts unchecked. Empty source and memory selections are valid.
3. Choose **local only** (the default), or separately choose the configured reasoner and review its displayed origin/model. Local mode always uses the local rule-based fallback, even if an HTTP provider is configured. A configured HTTP answer transmits the question and selected context to that provider and may incur that provider's charges; permission, retention and payment setup must already be appropriate. This development work made no real provider call.
4. Confirm this question and selection. The checkbox is consumed before any request. The browser requires a fresh preview and confirmation for another answer, including after failure, cancellation or a stale-state conflict. It never silently retries a submitted request.
5. The screen displays an answer only when its owner, scope, question, selected record contents, source/memory revision receipts, corpus and requested reasoner descriptor match the captured review. Those mechanical comparisons do not validate the answer's meaning or prove a remote server behaved honestly.

Question/scope changes invalidate the review. Account/API changes clear the token, question and private results; token changes clear private context and the draft question. Cancellation and late-response guards prevent an older request from repopulating a new view. Page exit/restore clears private state. There is no browser storage, microphone, speech, hardware or automatic memory-learning path on this page. Cancellation stops waiting, not an already accepted provider request. No absolute browser fetch deadline is implemented.

The page uses text rendering, not source-supplied HTML. Local Node DOM fixtures and actual Node fetch to Python loopback exercise it; real browser layout, CORS integration, accessibility and device behavior remain unverified.

## API contract

Both endpoints require the existing bearer-bound server identity. An optional `user_id` must match it; a client cannot select another owner's rows by knowing an ID or fingerprint. `/health` advertises `context_review_protocol: 1` without revealing private records or a configured provider.

`POST /v1/context/preview` accepts only `user_id`, `input` and `memory_scope`. The scope defaults to `default`. The input is limited to 10,000 characters, validated as UTF-8-safe text, and outer whitespace is trimmed before the reviewed question is fingerprinted. The input harm gate runs before retrieval; a rejected question returns an empty blocked preview and cannot be answered through this route.

The response includes:

- Exact trimmed question, owner/scope and `context_at`.
- `request_revision` binding that question, owner and scope.
- `corpus_revision` binding all records in this engine's admitted corpus snapshot.
- Up to five `canonical_evidence` candidates, each `{entry, revision}`, and up to five owned active `memories` with their existing state fingerprints.
- A sanitized `configured_reasoner` descriptor with kind, display target and opaque state revision, plus explicit limits.

Retrieval uses the existing bounded lexical/direct-first and graph-supplement logic. It is not semantic search or a relevance guarantee. The read transaction captures a coherent database snapshot; it writes no memory/audit data and releases the transaction before any later answer operation.

`POST /v1/context/answer` accepts only:

```json
{
  "user_id": "alice",
  "input": "The question shown in the preview",
  "memory_scope": "home",
  "confirm_context": true,
  "reasoner_mode": "local",
  "expected_request_revision": "64 lowercase hexadecimal characters from preview",
  "expected_corpus_revision": "64 lowercase hexadecimal characters from preview",
  "sources": [{"entry_id": "selected ID", "revision": "selected record fingerprint"}],
  "memories": [{"memory_id": 1, "revision": "selected memory fingerprint"}]
}
```

Those strings are explanatory placeholders, not valid example fingerprints. For `reasoner_mode: "configured"`, also include `expected_reasoner_revision` from the preview. In local mode omit that field entirely. `confirm_context` must be literal true. Source and memory arrays must be supplied, may be empty, are limited to five each, and reject duplicate IDs, unknown fields and malformed revisions. The API accepts identifiers/fingerprints only, never client-supplied passage or memory text.

Before dispatch the server checks the question/owner/scope, current admitted corpus, each exact source record, and authoritative memory ownership, scope, revision and expiration at a common selection time. Memory reads use one database read snapshot. Missing owned records fail without revealing another owner's existence; changed source/memory/configuration state returns a conflict. The server does not rerun retrieval or add graph candidates after selection. Returned source/memory order follows the supplied order.

The response is the ordinary thought result plus a `context_review` receipt containing mode, exact selected identifiers/fingerprints, question/corpus revisions, selected time and configured descriptor (or null for local mode). No learning is performed. The route discards action proposals and never executes actions. The existing input/output pattern gate and mechanical model-citation checks still apply; neither is a complete semantic safety boundary. Fallback after model failure uses only the captured selection.

## Configured model boundary

Only the exact built-in `LocalReasoner` and `HttpJsonReasoner` classes are available in configured selected-context mode. Custom implementations/subclasses remain available through the legacy path but cannot claim this flow's local/HTTP contract.

The descriptor displays the recipient origin and model, not credentials, URL path or query text. Its non-authorizing process-local identity/version changes when the configured instance, full endpoint, model, credential or transport instance changes. Secret material is neither displayed nor hashed into the public revision. These are state identifiers, not access tokens, persistent credentials or proof of human consent. Restarts or another HTTP adapter instance require a new preview; a load-balanced application needs an appropriate same-instance routing design rather than assuming revisions work across workers.

After validation, a private standard HTTP adapter is constructed from the captured endpoint/model/credential. Later mutation of the shared configured object cannot redirect that request or replace its transport. The selected path uses the standard no-proxy/no-redirect transport rather than a custom opener. HTTPS is required except for literal loopback IP HTTP. Provider response/request byte bounds still apply. The [standard isolated worker](MODEL_TRANSPORT.md) adds a parent-owned 30-second communication timeout and no automatic retry. This bounds the local network attempt subject to OS startup/termination, but does not cancel accepted provider work, ensure no charge or bound direct in-process engine-lock waits. A contending HTTP request is now [rejected before engine work begins](ENGINE_ADMISSION.md), with no automatic retry. No real provider compatibility has been validated.

## Resource and lifecycle limits

Candidate/selected context is capped at 48 KiB of serialized UTF-8 JSON. Preview and complete answer responses are capped at 64 KiB. Input and individual record limits also apply. Oversized data fails rather than silently truncating a private preference or passage. A generated answer can exceed the final response budget after a model was called; withholding it does not undo that call, so the browser reports uncertainty and does not retry. These byte/character limits are not tokenizer-specific token limits or full-process CPU/memory guarantees.

Read snapshots and fingerprints are not monotonic versions, consent receipts signed by a person, or single-use capabilities. The API checks the explicit confirmation on each request but does not store a consumed human-consent record; an authorized API caller can submit the same still-current selection again. The browser is stricter and requires a fresh preview after every attempted answer. Other same-owner clients retain their existing permissions.

Memory can change, expire or be deleted by another engine after the answer's read snapshot. Already captured/transmitted data and returned answers are not retroactively withdrawn. Similarly, later source-file changes do not revoke a running engine's immutable admitted corpus, and later credential revocation cannot recall an already dispatched request. This flow neither deletes data nor treats an API selection as approval to save/train/share it elsewhere. Ordinary chat can still use its separate recall/provider behavior.

## Local CLI and evidence

The trusted local CLI supports `jace preview-context USER QUESTION --memory-scope SCOPE` and `jace answer-context USER QUESTION`. The latter requires `--expected-request-revision`, `--expected-corpus-revision` and `--confirm-context`; repeat `--source ID REVISION` and `--memory ID REVISION` only for reviewed selections. Its default mode is local. Configured HTTP descriptors are process-local, so a preview from a separate CLI process cannot authorize a new HTTP adapter process: use the long-running API flow for configured answers. CLI users are trusted local operators, not bearer-isolated clients.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_context_review*.py' -v
```

Tests use synthetic memories and source bundles, temporary databases, mocked model responses, Node DOM fixtures and real local HTTP loopback. They cover selected-only dispatch, no provider on preview/default-local, owner/scope/expiry/revision rejection, source and configuration changes, coherent concurrent read snapshots, isolated dispatch configuration, empty selections, no action/learning, size failures, consent consumption, response binding and cancelled/stale UI flows. None proves semantic entailment, actual provider quality, full philosophical reasoning, real-browser behavior or production deployment readiness.

### Browser identity and confirmation binding

The page retains account, API origin, token and scope identity independently of a preview or answer. A new preview cannot silently rebind a retained question or token after an identity change. Reset paths (including Cancel, token edits and scope/question events) also clear the credential and question if the owner or API origin silently changed. Explicitly enter the new credential and question after resetting the identity.

A checkbox change records confirmation for that exact preview, selected context and reasoner mode. A restored checked property alone cannot authorize an answer; silent selection or local/configured-mode changes consume and reject the old confirmation. The selected question, account, scope and configured descriptor remain bound to the validated preview. During requests, identity, question and visible selection/mode state are checked before and after every streamed body read. Detected drift cancels the reader without consuming another chunk, suppresses stale results and requires new review; it cannot undo a request already received by the API or provider.

Synthetic DOM regressions cover retained drafts and completed answers, reset rebinding, restored confirmation, silent selection/mode changes and per-chunk cancellation across health, preview and answer responses. Intended confirmations in the fixtures invoke the checkbox change handler. This is not proof of real browser autofill, user-generated event provenance, rendering or production deployment behavior.
