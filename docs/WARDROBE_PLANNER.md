# Explicit wardrobe inventory and review

The research brief's wardrobe example asks the system to inventory actual needs, re-wear and repair before considering purchases. This implementation takes a bounded step: the user declares an inventory and category minimums, then a local rule-based planner builds item-specific review steps. It does not infer clothing needs, inspect garments, learn a model, interpret sacred texts or perform actions.

## Use the screen

With an already configured, owner-authorized local API, serve the source checkout's web directory:

```sh
python -m http.server 8080 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:8080/wardrobe.html`, also linked from the conversation and other planning pages. Enter the exact assigned owner, scope, trusted API origin and token. No credentials are provisioned or copied between pages. The API must already permit the page's origin. Static web files are part of the checkout, not the Python wheel.

Add item rows and explicitly choose each field, including ownership and preservation. Choose all five minimums; zero is an explicit choice, not a default. Leave a new inventory's expiry blank only if indefinite future eligibility is intended. Review and check the save box before saving. That single-use choice is bound to all raw visible fields and the current owner, scope, token and API text, then consumed before validation or waiting for the API. Changed fields require another check; a restored checked box alone is not consent. Save does not automatically plan. Its response must preserve the exact submitted expiry instant (including microseconds and UTC/offset normalization), or null for no expiry. An edited inventory must retain the reviewed expiry. A mismatched response is treated as an uncertain write, never a confirmed save. Review the displayed saved inventory, then explicitly request its checklist.

Load existing inventories through **Load saved inventories** and select the intended record. Nothing chooses the newest inventory automatically. Pages fetch 20 owned memories in the selected scope and show only typed inventories, including expired records. Non-inventory records still count toward page size and are transmitted to this authorized client. Continue paging as needed. Review fetches a fresh owned record. Edits require another confirmation and a matching state fingerprint; dirty forms cannot generate a plan until saved or freshly reviewed again.

Use the memory manager for expiry, renewal and individually confirmed deletion. Generic text correction cannot edit typed inventories. Updating the inventory preserves its owner, scope and expiry. Creating another inventory does not supersede an existing one. This slice supplies browser/API access, not a dedicated wardrobe CLI command.

## Exact input and bounds

An inventory has exactly `items` and `minimum_ready`.

Each of 1–30 item rows has exactly:

- `label`: 1–60 trimmed characters, without Unicode control/format characters. Labels must be distinct ignoring NFC composition and casefold. Original label text is retained. Use ordinary labels, not secrets or another person's private details.
- `category`: `tops`, `bottoms`, `outerwear`, `footwear`, or `other`.
- `quantity`: integer 1–100, not a boolean/fraction; all quantities total at most 300 units.
- `condition`: `ready`, `repair`, or `uncertain`.
- `fit`: `fits`, `does_not_fit`, or `uncertain`.
- `use`: `regular`, `occasional`, `unused`, or `uncertain`.
- `preserve`: an explicit boolean. False does not authorize disposal.
- `ownership`: `mine`, `shared`, `others`, or `uncertain`.

`minimum_ready` requires all five category names, each an integer 0–50. A row groups units with the same declared attributes. Use consistent units, such as pairs for footwear, in quantities and minimums. Different labels do not prove different physical objects; the planner cannot detect double counting, infer units or assess whether the chosen minimum is adequate.

Canonical typed JSON is bounded by the existing 10,000-character memory limit. Unknown fields, aliases, malformed types, duplicate labels and bounds violations fail closed. If the existing memory filter would redact/alter the encoded inventory, the whole write rolls back rather than storing a malformed or unreviewed typed record. This filter is heuristic, not proof that labels contain no sensitive data.

## What the plan calculates

An **owned-ready** unit has all three declarations: ownership `mine`, condition `ready`, fit `fits`. Only those units count toward the category's minimum, including units the user preserves or seldom wears. A category's shortfall is `max(0, minimum − owned-ready)`. It calls for needs/inventory review, not buying instructions.

For each row, the first matching decision is used:

1. Shared, other-owned or uncertain ownership: leave unchanged and review ownership/permissions.
2. Explicit preservation: preserve, while checking condition/fit before use.
3. Repair condition: assess appropriate repair feasibility, existing supplies and required skills. No cost, success or savings is assumed.
4. Uncertain condition, non-fitting/uncertain fit or uncertain use: review; uncertainty is not evidence for disposal/replacement.
5. Explicitly unused, owned, ready, fitting, unprotected units: consider a reversible **possible-surplus review**, but only up to the category's owned-ready count minus the declared minimum.
6. Other suitable units: re-wear/recombine and consider storage already owned; unused units without surplus remain available against the declared minimum.

The possible-surplus budget is consumed in entered row order across candidate rows. This is deterministic allocation, not optimization or advice to choose one garment over another. A candidate quantity does not recommend or authorize donation/disposal. Seasonal, work, health, belief and sentimental needs may be missing. Any later transfer requires the owner's separate decision and a willing recipient's acceptance. No contact, purchase, repair or physical action occurs.

Summary fields are declared counts only:

- `declared_total_units`: all item quantities.
- `owned_ready_units`: the three-condition rule above.
- `repair_review_units`: mine and declared repair condition.
- `uncertain_review_units`: mine and condition uncertain, fit not `fits`, or use uncertain.
- `protected_units`: every `preserve: true` row, regardless of other attributes.

These categories overlap and must not be summed. For example, a protected repair item appears in both summary counts while its item decision is **preserve**. No mass, water, energy, carbon, material savings or environmental benefit is calculated.

## API and lifecycle

- `POST /v1/wardrobe-inventories`: `inventory`, literal `confirm_save: true`, optional `memory_scope`/`expires_at`. Optional `user_id` must match the bearer subject. Returns `{memory, notes}`.
- `PATCH /v1/wardrobe-inventories`: `memory_id`, complete replacement `inventory`, required `expected_revision`, literal `confirm_save: true`. The owner/revision/type checks and memory/graph/audit update are one transaction. A stale revision returns 409; another owner's ID returns 404.
- `POST /v1/plans/wardrobe`: optional `memory_scope`, `inventory_memory_id`, `expected_inventory_revision`. The revision requires an explicit ID. The browser always sends both. Planning rechecks owner, scope, type, expiry and the same fetched record's state fingerprint. It returns counts, category shortfalls, item review steps, applied inventory, source qualifications and `actions_executed: false`.

Without an explicit ID, no active typed inventory produces `needs_inventory`; several produce `choose_inventory` without steps. Malformed active candidates fail closed. Discovery retains existing scan budgets and a 25-active-record cap; an explicit ID avoids broad discovery. Plain memories containing inventory-looking JSON are not promoted. Source tags are app conventions, not cryptographic provenance against a trusted database operator.

Fingerprints are not secrets, permissions or monotonic versions. Exactly restored identical state has the same fingerprint. The plan uses one fetched snapshot; later edits, expiry or deletion do not retract it. Legacy callers may omit the optional planning fingerprint and receive the latest eligible row. Summary calculations do not automatically update a displayed plan.

## Privacy and verification boundaries

The dedicated planner never calls a model. Typed inventories remain ordinary private memory records, so ordinary chat can separately recall/transmit them under its existing configured-provider behavior; this feature does not grant that sharing permission. Scopes filter context, not other clients authenticated as the same owner.

The screen uses capability checks, captured owner/scope/credentials, explicit consumed consent, identity/destination resets, text-only rendering, bounded streamed responses, no cookies/storage and no redirect following. Identity is bound separately from the selected record. Input/change events and checks before operations and across asynchronous response reads invalidate changed state, including unnoticed field changes. Planning checks the visible form against the saved review. Cancel or a scope reset cannot rebind a retained token to a silently changed owner or API. Same-owner/same-API scope changes can retain the token, but clear private drafts/views. Page exit and page show/restore clear token and state. Context changes, pending form edits and cancellation ignore late callbacks. An accepted server write can still complete after cancellation; unknown writes are never automatically retried. Reload to inspect actual state before another attempt. There is no absolute fetch deadline.

Tests use original synthetic inventory records and temporary stores. Backend tests cover schema limits, all categorical combinations, surplus budget/minimums, ownership, conflict and concurrent update, expiry/deletion, generic-edit blocking, graph-failure rollback and filter-altered-label rollback. UI fixtures and actual Node-to-Python loopback tests exercise confirmed save/review/update/plan and privacy/failure flows, including snapshot-bound consent, silent identity/form drift, reset paths, streamed-body invalidation, restored checkbox/page state and uncertain submitted writes. These guards detect changed state at event/request/read boundaries, not malicious page scripts/extensions, silent changes restored before a checked boundary, or immediate idle-page erasure. They do not replace server authorization. The fixtures are not real-browser, real-garment, scholarly, model-quality or physical-safety validation; actual browser autofill, back/forward restoration, layout and accessibility remain unverified. Built-in principle records remain unverified summaries, not Agama quotations.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_wardrobe_inventory.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_wardrobe_planner_ui.py' -v
```
