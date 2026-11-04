# Forget one owned memory

A user can now remove one active memory without deleting their other active memories. HTTP ownership comes from the configured bearer token, never a client-supplied user ID. The local CLI is a trusted operator interface to its local database, not an authenticated multi-user service.

## Review and confirm in the CLI

```sh
python -m jace.cli memories alice
python -m jace.cli forget-memory alice 12
```

`memories` shows the owner's 20 most recent records and IDs. `forget-memory` without flags is a **preview only**: it shows the selected memory, deletion effects, the number of unattributed audit entries and a warning. It does not delete a memory. After reviewing it:

```sh
python -m jace.cli forget-memory alice 12 --confirm-delete
```

Old audit rows have no reliable memory ID. Some rejected memory attempts are also unattributed. If any exist for this owner, the command stops without deleting anything and explicitly explains that cleanup will remove **all of this owner's unattributed audit entries**, not just an inferred subset. To accept that additional loss, use the separate choice:

```sh
python -m jace.cli forget-memory alice 12 --confirm-delete --confirm-all-unattributed-audit-cleanup
```

This preserves other active memories and their attributable audit entries. It never removes another user's audits. Unattributed entries are not assigned to a memory by guessing from their text. The required extra choice is checked again inside the deletion transaction, so new unattributed rows appearing after the preview do not get silently removed under only the first confirmation.

## Authenticated HTTP interface

1. `GET /v1/memory-item/12` previews only the bearer subject's item and the same cleanup warning. Missing or another user's item returns 404.
2. `DELETE /v1/memory-item/12` requires `X-JACE-Confirm-Delete: 12` in addition to bearer authorization.
3. If unattributed audits exist, deletion returns 409 without modifying the stores, states their count and requests the separate `X-JACE-Confirm-Audit-Cleanup: all-unattributed-for-owner` choice. Resubmit only after the user accepts that scope.

IDs must be canonical positive ASCII decimal 64-bit integers. Query parameters, encoded/ambiguous IDs, duplicate confirmation headers and nonzero/ambiguous body framing fail closed. The new item route is distinct from the pre-existing `DELETE /v1/memory/<user_id>` whole-user deletion route. Whole-user deletion behavior has not changed.

Clients should present the preview and any cleanup warning before collecting confirmation; a supplied header is a caller assertion of that choice, not proof of a human UI interaction. The browser voice console does not yet include a memory-management screen. No production credentials are supplied by this feature.

## Atomicity, privacy and limits

New accepted/correction audit records carry the memory ID and still contain no memory plaintext. Existing audit tables migrate without discarding entries or guessing their associations.

The engine reserves a SQLite writer transaction before looking up the owned item. The selected memory, its associated graph node/edges, its attributable audits and explicitly approved unattributed owner audits are deleted together. A failure rolls back all of them. Other engine processes cannot insert a correction between the lookup and deletion; a later correction gets not-found rather than recreating the deleted record. A new memory created after deletion is preserved.

Single-item deletion touches only the graph node for the selected ID. Historical orphan graph records with no reliable connection to that ID are not guessed or broadly purged. Whole-user forgetting has separate exact-owner legacy cleanup. This is logical deletion from the live database, not guaranteed erasure from SQLite remnants, backups, previous exports, external model providers or unknown historical copies. Those require a separately reviewed retention/erasure process.

The tests use synthetic records and temporary databases. They cover ownership, both explicit choices, legacy migration, preserved unrelated data, rollback after graph mutation, concurrent correction/new writes, stale audit previews, CLI preview/confirm behavior and HTTP framing. No real user's memories were deleted during development.

Named recall scopes do not narrow the existing owner-ID management operations. The deletion preview includes the selected record's scope. The optional broader cleanup removes all unattributed audit entries for that owner across all scopes. Whole-user forgetting removes every scope. See [scope behavior](MEMORY_SCOPES.md).
