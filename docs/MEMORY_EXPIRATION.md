# Explicit memory expiration

A temporary preference or plan need not remain eligible for recall indefinitely. The owner can now give a memory an exact expiration time. This is a recall control, not deletion, automatic temporal reasoning, or a retention policy.

## Choose an expiration

The trusted local CLI accepts:

```sh
python -m jace.cli remember alice "I prefer quiet rooms during this visit" --expires-at 2026-12-01T18:00:00Z
python -m jace.cli set-memory-expiration alice 1 --at 2026-12-02T23:30:00+05:30
python -m jace.cli set-memory-expiration alice 1 --never
```

The last command explicitly removes expiration, making the record eligible for recall again. The CLI is a trusted local operator interface, not an authentication boundary. HTTP operations require the owner's assigned bearer token:

- `POST /v1/memory` accepts optional `expires_at` alongside `content`. Omission or JSON `null` creates a record without expiration.
- `PATCH /v1/memory-expiration` requires `memory_id` and `expires_at`. A timestamp sets expiration; JSON `null` explicitly removes it. Omitting the field is rejected rather than silently clearing it.
- The authenticated subject, not a client-supplied user ID, determines ownership. Another owner's record and a missing record both return 404.
- Memory review responses, including `GET /v1/memory/<user_id>` and the single-item deletion preview, include `expires_at`. Review deliberately includes expired records.

Use a full date and time with `Z` or an explicit numeric offset. Fractional seconds of up to six digits are supported. Dates without a time, timestamps without a timezone, unknown `-00:00` offsets, leap seconds, invalid dates and malformed offsets are rejected. Accepted times are normalized to UTC. Past times are allowed as an explicit way to immediately disable future recall. No date is inferred from a sentence such as “until tomorrow.” Conversation learning still has no expiry by default; use the explicit creation or update interface when a duration is wanted.

## Recall boundary

At context selection, a record is eligible if it has no expiration or its expiration is strictly later than the server's current UTC time. Equality means expired. Direct lexical search, the no-word recent-memory fallback, graph seed/expansion and the final graph-to-memory selection all enforce this rule. Malformed timestamps already in storage fail closed for recall. Canonical source records are not given private-memory expiry rules.

One context-build timestamp is used across the engine's direct and graph retrieval. Expiration is checked when context is selected, not continuously during a model call. It does not retract a context already selected, cancel an in-flight request, remove past responses, or remove data previously sent to a configured external model. The server's wall clock must be trustworthy; a clock rollback can make a time-limited record eligible again. This is not a monotonic revocation system.

Expired content and graph nodes stay on disk and can be reviewed, explicitly corrected, renewed, or deleted by the owner. Content correction preserves expiration and does not silently renew a record. To remove records, use the separately confirmed [single-item deletion](MEMORY_DELETION.md) flow or whole-user forgetting. Neither expiration nor logical deletion guarantees erasure from SQLite remnants or backups.

## Storage and tests

Startup adds a nullable expiration column under a writer-reserved transaction. Existing records keep their contents, IDs, creation times and no-expiration behavior. Expiry changes and a text-free, item-attributable audit event commit in one transaction. Graph retrieval reads expiry from the owned memory row, so there is no separate graph timestamp to drift. Concurrent correction and expiry changes serialize through SQLite's writer transaction.

Synthetic regression fixtures cover exact before/equal/after boundaries, timezone normalization, invalid inputs and stored values, direct/graph/reasoner context, owner isolation, no-word fallback, old-schema migration and rollback, audit-write failure, concurrent correction, explicit renewal, HTTP authorization and CLI behavior. They do not establish automatic contradiction resolution, agent/session scopes, production retention compliance or real model quality.
