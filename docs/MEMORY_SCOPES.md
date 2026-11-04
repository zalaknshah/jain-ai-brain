# Explicit memory scopes

Named scopes separate one owner's recall contexts, for example `home` and `work`. A request uses only the selected scope. It does not automatically mix in `default` or choose a scope from the subject of a conversation. This is context organization, **not a separate authorization boundary**: a bearer token for an owner can select any of that owner's scopes. Untrusted agents must not be given the same owner token on the assumption that a scope name limits their access.

## Choose a scope explicitly

```sh
python -m jace.cli remember alice "I prefer quiet rooms" --memory-scope home
python -m jace.cli ask "What should I consider for a quiet room?" --user alice --memory-scope home
python -m jace.cli ask "Remember I prefer repair before replacement" --user alice --memory-scope work --learn
python -m jace.cli memories alice --memory-scope work
python -m jace.cli memory-scopes alice
```

The CLI is a trusted local operator interface, not per-user authentication. Scope IDs are 1–64 lowercase ASCII letters/digits, with underscores or hyphens allowed after the first character. This restriction applies to identifiers, not the language of memory text. Invalid values, including an explicit blank or null, are rejected. Omitting the selector uses `default`; values are never silently trimmed, case-folded or inferred.

HTTP requests remain bound to the authenticated bearer subject:

- `POST /v1/think` accepts `memory_scope`, applies it to recall, and echoes it in the result. If `learn: true`, explicit preference/fact learning uses that same scope.
- `POST /v1/memory` accepts `memory_scope` alongside content and optional expiration.
- `GET /v1/memory/<user_id>?memory_scope=home` reviews recent stored records in exactly that scope, including expired records.
- `GET /v1/graph/search?q=quiet&memory_scope=home` searches canonical records and eligible memories from exactly that scope.
- `GET /v1/memory-scopes` lists this owner's valid stored scope names, plus `default`. It accepts no user selector. A named scope appears when its first memory is saved; it disappears when its last record is deleted. Expiration alone does not remove it.

Scope query parameters and body fields must be unambiguous. The think, remember, correction and expiration routes accept only their documented JSON fields; misspelled aliases such as `scope` do not fall back to default. `learn`, when supplied, must be a boolean. Unknown or duplicate parameters on scoped read routes, malformed scope values and duplicate JSON body keys are rejected. A valid name with no records returns no private memories, rather than falling back to another scope.

## Storage and lifecycle

Startup adds a `memory_scope` column and an owner/scope/ID index within a writer-reserved transaction. All existing records become `default` without changing their ID, text, creation/update time, expiration or audit associations. Text mentioning “home” or “work” is not reclassified. Failed migration rolls back the new column/index.

Direct memory search, the no-word recent-memory fallback, graph seed/expansion and the final graph-to-memory selection use the same exact owner/scope pair. Canonical records remain shared subject to the existing admitted-corpus boundary. A graph edge to a memory in another scope does not admit that memory into traversal or the model context. There is no mutable server-wide “current scope”; concurrent requests carry their own selectors.

Content correction and expiration changes preserve the record's original scope. Passing `memory_scope` to those PATCH operations is rejected instead of silently moving a record. This version has no move/rename operation. If a separate memory is needed elsewhere, create it explicitly and use the confirmed deletion flow for the old record when appropriate.

Single-item review, correction, expiry and deletion remain owner-ID management operations. They can address any owned record and report its scope. Whole-user forgetting removes every scope for that owner. The separate consent required for unattributed audit cleanup applies to **all that owner's unattributed audit entries across all scopes**, not just the selected item or context. Other active memories and attributable audits remain protected by the existing single-item deletion rules. See [deletion scope and confirmation](MEMORY_DELETION.md) and [expiration boundaries](MEMORY_EXPIRATION.md).

## Console behavior and compatibility

The conversation console has an explicit memory-scope field. Changing it clears the old draft, response, read-aloud state and one-message learning choice, invalidates pending callbacks and requests cancellation of in-flight browser work. It keeps the token because the owner and API destination have not changed. New dictation callbacks from the previous scope are ignored.

Before sending a question, the console checks the API's public `/health` response for `memory_scope_protocol: 1`. The capability request contains no question, source context or learning payload. An old or incompatible API is rejected before the question is posted. The answer must also echo the requested scope; otherwise it is not displayed or read aloud. A scope switch while the capability request is pending prevents the subsequent question from being sent.

This handshake detects ordinary old-server incompatibility; it does not prove that an untrusted server implements the declared behavior. Upgrade every process accessing a shared database. Older engine code does not understand scope filtering and must not run against the same database. Custom clients must send the selector explicitly when they want a non-default scope.

Cancellation cannot retract a request already accepted by the server. Such a request may still finish or save an opted-in memory in its original scope. Changing scopes does not migrate that memory, erase prior responses, retract external-model context or delete records. Real browser/microphone behavior remains unverified; the console evidence comes from deterministic Node-based API fixtures.

## Evidence and remaining limits

Regression tests cover direct/graph/reasoner isolation, owner separation, invalid selectors, default migration and rollback, concurrent engine writes, correction and expiry preservation, single/whole-user forgetting, HTTP/CLI behavior, and console scope-switch/compatibility races. Tests use only synthetic data and local temporary databases/loopback services.

Scopes do not implement automatic topic classification, independent agent permissions, session expiry, semantic contradiction resolution or a production retention policy. The operator must select the intended context and separately authorize any configured external model provider's receipt of selected private data. No source ingestion, training, external model call or credential provisioning is performed by creating a scope.
