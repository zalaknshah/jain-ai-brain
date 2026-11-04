# Optional model output and source boundary

The optional HTTP model adapter now requires structured answers and performs mechanical source checks before displaying a model response. This reduces specific fabricated-citation and malformed-output paths. It does **not** establish semantic entailment, source correctness, Jain reasoning, prompt-injection resistance, truthfulness or harmlessness. No real provider or model compatibility has been validated by this slice.

## Contract and source checks

The configured chat-completions endpoint receives a JSON-object response request. Its sole completed assistant choice must contain a JSON object with exactly:

```json
{
  "answer": "Generated plain-text suggestions, without inline bracketed references.",
  "citations": [
    {"entry_id": "an-id-from-this-request", "quote": "An exact excerpt from that record's principle field."}
  ]
}
```

An empty citation list is allowed and explicitly labeled as lacking a reviewed excerpt. Each supplied citation must identify an unambiguous record retrieved for this request, with `verified: true` and nonempty work, source, language, location and license declarations. Built-in unverified sample summaries are not citable. A quote must be a nonempty, exact contiguous substring of that record's `principle`, not its generated interpretation/guidance field. Unknown IDs, duplicate citations, altered text, invented metadata fields, duplicate JSON keys, extra action fields, terminal control characters and inline bracketed reference labels are rejected.

The response permits an answer of at most 8000 characters, at most five distinct citations, at most 600 characters per quote and at most 16000 characters in the JSON content. Only the server renders citation metadata, copied from the admitted local record. Generated answer text is labeled as not independently verified. Matched excerpt blocks explicitly say that matching does not establish support for the answer and that review/licensing remain declarations.

These checks do not establish that a quote is representative, complete or relevant. They cannot prove the truth of a claim, detect every false attribution written in ordinary prose, independently verify a source/license, or prevent a model from following malicious instructions in supplied data. The prompt identifies source records and memories as untrusted data; that instruction is guidance, not a security guarantee. Only the server-rendered excerpt block has the mechanical checks described here.

## Transport and failure behavior

The operator's endpoint must use HTTPS, except that plain HTTP is allowed for literal loopback IP addresses such as `127.0.0.1` or `::1`. Public plaintext HTTP, embedded URL credentials, fragments and invalid authorities are rejected before opening a connection. The hostname `localhost` is intentionally not an exception: use a literal loopback address for local testing.

Redirects are not followed, including redirects to another path on the same host. Inherited HTTP proxy settings are disabled for this adapter so selected user context and authorization are sent directly to the configured target. Provider setup that requires a proxy or redirected endpoint must be reviewed separately; the adapter does not discover or authorize an alternative destination.

The JSON request body is capped at 128 KiB; excessive context is rejected rather than silently truncating a user's preference. The response body is read with a 64 KiB cap. Only status 200 and identity response encoding are accepted. The configured 30-second socket timeout is a **per-I/O/inactivity timeout**, not a complete request deadline, DNS bound, model cancellation or defense against every slow trickle response. The engine's existing global request lock and lack of model cancellation remain limitations.

Malformed, oversized, incomplete or unavailable responses use a labeled local rule-based fallback. Raw provider errors and rejected output are not echoed. Standard assistant refusal fields and `content_filter` completion results instead produce a fixed refusal with no action. A well-formed refusal dominates incomplete, missing or tool-related finish metadata; it is not replaced by a local navigation proposal.

Model-supplied tool calls and action fields are never executed or interpreted as authorization. The existing local request-based navigation proposal can still be returned on a normal answer or local fallback; it requires explicit confirmation and has no hardware execution path. The engine also rejects malformed custom-reasoner output and proposals lacking the strict confirmation flag. Returned text still passes through the existing English pattern-based harm filter. None of these mechanisms constitutes complete semantic safety.

Configuring a provider still sends the request and selected private memory/source context to that provider. Obtain the appropriate consent, review retention and charges, and provision credentials separately before enabling it. This development work made no external model call and created no credential.

## Offline evidence

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_model_output.py -v
python scripts/evaluate_model_output.py
```

Tests use original synthetic records, mocked chat-completion envelopes and a real loopback HTTP server with a synthetic token. They cover the three original practical examples, exact and altered quotations, unknown/unreviewed sources, source-metadata copying, malformed completion payloads, explicit refusal precedence, byte limits, redirect rejection and generic reasoner/action boundaries.

The separate 12-case fixture evaluation checks mechanical admission, including an original Gujarati sentence. It does not contact a provider, use collected religious texts, measure scholarly accuracy or demonstrate multilingual reasoning. Successful fixture results must not be presented as real model performance or a completed grounded-answer product.
