# Browser memory manager

The browser console now links to `web/memory.html`. This is a functional client for reviewing saved records and making explicit changes through the authenticated local API. It does not infer facts, resolve contradictions, call a model, train on memory, or create credentials.

## Start and use

Run the Python API with your already-authorized operator configuration, then serve the checkout's web directory as described in the README:

```sh
python -m http.server 8080 --directory web
```

Open `http://127.0.0.1:8080/memory.html`. Web assets live in the source checkout, not the Python wheel. Enter the exact assigned user ID, token, memory scope and trusted API origin, then choose **Load newest memories**. Nothing loads automatically. The token is kept in the current page only; it is not transferred through a link, copied from the conversation page, stored in localStorage or sent to a model. HTTPS is required outside literal local loopback/localhost HTTP. The API must already permit the page's origin. No deployment or token provisioning is provided here.

Each page contains at most 20 owned records in one exact scope, including expired records. **Older page** replaces the view; **Load newest memories** starts again. Selecting **Review this item** fetches a fresh owner-bound record and deletion preview. The saved text is displayed separately from the editable, unsaved correction.

- **Save corrected text** explicitly replaces that item's text after the existing alignment filter. Typed cleaning profiles and wardrobe inventories are read-only here for text changes; use the matching typed API or dedicated [cleaning](CLEANING_PLANNER_SCREEN.md)/[wardrobe](WARDROBE_PLANNER.md) screen, while expiry and deletion stay available. It does not move scopes or change expiration.
- **Set recall expiry** uses an explicit timezone timestamp. **Allow recall without expiration** explicitly removes expiry and may make an expired memory eligible again. Neither action deletes the record.
- **Delete reviewed item** requires an unchecked-by-default item-deletion choice. If unattributed audits exist, a separate unchecked choice explicitly covers **all current unattributed audit entries for this owner across every scope**, including legacy entries. Other active memories and attributable audits remain. The preview count can change; the optional revision condition covers the memory record, not these unrelated audit rows.

Deletion is logical live-store deletion, not assured erasure from SQLite/WAL remnants, backups or external providers. There is no bulk-delete control in this screen.

## Conflicts, cancellation and identity boundaries

Every new-screen correction, expiry change and deletion carries the reviewed record's SHA-256 state fingerprint. The API compares it inside the existing writer-reserved transaction before mutation or audit writes. A conflicting update yields HTTP 409 and requires reloading, with no automatic overwrite or retry. A graph failure still rolls back the whole correction.

The fingerprint covers the complete stored memory state, including owner, scope, content and timestamps. It is not a secret, authorization grant or monotonic revision counter. An exactly restored identical state has the same fingerprint. Legacy API/CLI callers remain supported and can omit the optional condition, so unconditional writers still exist.

Changing user or API origin clears credentials, private views and drafts. Changing token or scope clears the view/drafts and invalidates pending callbacks; scope changes retain the token for the same account/destination. Page exit clears the token and view. Only one screen operation can be pending. Deletion checkboxes are consumed before submission, and editing clears them.

**Cancel and clear view** stops waiting and discards late callbacks. A mutation already accepted by the server may still complete. Network errors or uncertain responses clear the selected item; reload its actual state before deciding whether another action is needed. No automatic retries occur. There is no absolute network deadline; cancellation is available.

The screen negotiates `memory_management_protocol: 1` before authenticated requests, refuses redirects, omits browser cookies, requests no-store caching and caps streamed JSON at 1 MiB. Memory content is displayed with `textContent` or textarea values, not interpreted as HTML. These controls do not make an untrusted API trustworthy or prove end-user identity beyond the existing bearer-token mapping. Choose the destination carefully.

## API additions

- `GET /v1/memory/<owner>?memory_scope=home&limit=20&before_id=123` returns `memories`, `memory_scope`, and `next_before_id` (integer or null). `limit` is 1–100; omission remains 20. `before_id` is a canonical positive 64-bit integer. Unknown, duplicate and malformed query fields are rejected. SQL always binds the authenticated owner and exact scope.
- Returned memory dictionaries include `revision`, the state fingerprint.
- `PATCH /v1/memory` and `PATCH /v1/memory-expiration` optionally accept exact `expected_revision` strings. Explicit null/malformed values are rejected; omission preserves prior behavior.
- `DELETE /v1/memory-item/<id>` optionally accepts one `X-JACE-If-Memory-Revision` header alongside the existing explicit deletion/cleanup confirmation headers. Duplicate or malformed revision headers are rejected.

Pagination uses descending IDs, not offsets. Newer insertions do not shift older-page boundaries, but the pages do not form a database snapshot; concurrent correction/deletion is reflected when subsequent pages are read. The screen restricts IDs to JavaScript safe integers even though the backend supports the wider positive 64-bit range. Older oversized records or malformed responses may fail the screen's limits; no records are silently truncated or deleted.

## What was exercised

Backend tests cover pagination, owner/scope boundaries, exact revision admission, all three stale mutation paths, rollback and two concurrent engines attempting a change from the same reviewed state. Node interaction fixtures exercise confirmation, repeated actions, correction/expiry, stale identity/destination results, cancellation during a write, conflicts, pagination, unsafe URLs, old-server capability failure, content-as-text and response-size limits.

Additional tests run the actual JavaScript client with Node's streaming HTTP fetch against the actual Python API on loopback and temporary synthetic databases: full review/correction/expiry/confirmed deletion, another-client conflict and wrong-owner access. These use original fixture text and clearly synthetic test credentials only.

The DOM is a test harness. Real browser rendering, accessibility-device behavior, CORS enforcement by a browser, browser credential managers and end-user browser integration remain unverified. No earlier denied browser launch was retried.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_memory_management.py -v
PYTHONPATH=src python -m unittest discover -s tests -p test_memory_manager_ui.py -v
```
