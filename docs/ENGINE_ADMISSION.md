# Nonqueued HTTP engine admission

The local API now rejects an engine-backed request when the same engine instance is already working, instead of letting that request wait behind the engine lock. This prevents a rejected write from silently starting later after the first operation finishes. It does not cancel work that was already admitted, introduce parallel model execution or qualify production hosting.

## Contract

Authorization, ownership checks performed by the route, request framing, body reads and JSON parsing still happen before engine admission. The first engine access attempts to acquire the engine's existing reentrant lock without waiting. A contending request receives HTTP 503 with:

```json
{
  "error": "The engine is busy. No engine work was started; review before retrying.",
  "code": "engine_busy",
  "request_started": false,
  "automatic_retry": false
}
```

Here `request_started: false` means no **engine operation** began for that request. The server did receive and authenticate the request, and may already have parsed its JSON body. This is distinct from the existing connection-capacity 503 and rate-limit 429 responses. The busy response intentionally has no Retry-After header: it does not promise capacity at a particular future time or ask clients to retry automatically.

The server does not queue or retry that rejected operation. Its data is not written to memory, its reasoner is not called, and its deletion or update is not performed. Review the operation and current state before explicitly submitting a new request; a separate attempt is not idempotency protection. Never infer "not started" from a timeout, broken connection or arbitrary 503 response. Only the specific received `engine_busy` response has this pre-admission meaning.

One admission spans the entire HTTP handler, including ordinary thinking and any explicitly requested learning from the same request. Nested engine calls reuse the reentrant lock. The admission is released in guaranteed handler cleanup on success, validation failure, unexpected failure or a disconnected client. Existing API authentication, per-message learning consent, state-revision checks, source boundaries, deletion confirmation and selected-context controls remain in force.

All current engine-backed routes use the same boundary, including canonical search, context review, memory reads/changes, cleaning and wardrobe workflows. Public `/health`, OPTIONS, unknown routes standalone motion decisions and stateless dispute preparation do not acquire the engine lock. These routes remain subject to existing connection, rate and request-read limits; health is not an unconditional availability guarantee.

## Remaining limits

- An admitted operation may finish, write or transmit provider context after its client disconnects. This change supplies no rollback, cancellation or safe automatic retry of an uncertain outcome.
- The admission remains held through response writing. A slow reader can retain it until normal socket timeout/error. It does not provide a hard real-time latency guarantee or release all capacity at a precise time.
- Direct in-process engine calls retain their previous blocking semantics. The same lock ensures an HTTP request also rejects contention from those callers. The gate is per engine instance, not distributed across processes or different engines sharing SQLite.
- There is no fair queue, per-owner scheduling or reserved capacity. A long operation can prevent other owners' engine-backed requests from being admitted; they now receive a prompt rejection rather than wait to execute later.
- Custom reasoners and other admitted work are not made cancellable or time-bounded by this gate. The optional standard HTTP model worker has its [separate local communication timeout](MODEL_TRANSPORT.md), which cannot cancel already accepted provider work or charges.

## Offline evidence

`tests/test_engine_admission.py` uses synthetic event-gated reasoners, temporary memory databases and real local HTTP requests. It checks every current engine-backed route under contention, no rejected writes/reasoner calls after release, thinking-plus-learning as one admission, public health, auth/ownership/JSON errors, incomplete authenticated bodies without premature admission, direct engine contention, nested calls, cleanup after errors and client disconnects. A disconnected admitted request is explicitly tested to finish its requested learning, documenting the uncertain-outcome limit rather than claiming cancellation.

These are local functional regressions, not production capacity measurements or real browser/provider qualification. No credentials, external provider calls, new corpus data or paid compute are required.
