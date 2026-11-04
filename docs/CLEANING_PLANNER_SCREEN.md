# Explicit cleaning planner screen

`web/cleaning.html`, linked from the conversation console and memory manager, makes the existing typed-profile API usable without command-line profile commands. It is a local conditional checklist builder, not a model, general household planner, religious authority or robot controller. It does not inspect surfaces, infer preferences from chat, make purchases or perform cleaning.

## Open locally

Use an already configured local API with an assigned owner-bound token and permitted page origin. Do not put tokens into source files or URLs. This guide does not provision credentials or deploy a service.

From the source checkout, serve the static pages on loopback:

```sh
python -m http.server 8080 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:8080/cleaning.html`. Enter the exact assigned user, scope, trusted API origin and token. HTTPS or literal loopback/localhost HTTP is accepted; path suffixes, credentials, whitespace, query strings and fragments are rejected. Never send a token to an API you do not trust. Pages do not copy tokens between one another or save them in browser storage. Web assets remain in the source checkout, not the Python wheel.

## Create, review, build

1. Choose all four fields. No surface, water, time or supply choice is preselected. Read the conditional surface/product/hygiene guidance. New profiles can have an explicit timezone expiry; blank means no expiry.
2. Select the unchecked save-consent box and choose **Save new profile**. Editing any field clears this choice. The choice is consumed before waiting for the API. Save does not automatically build a plan. The response must preserve the submitted expiry instant, including microseconds and offset normalization, or null for no expiry; updates must retain the reviewed expiry. A mismatched response is treated as an uncertain write.
3. Review the saved choices and ID shown separately from the editable form. Choose **Build checklist from these saved choices**. The screen sends that exact ID and reviewed state fingerprint.
4. Read all conditional steps, evidence qualifications and limits. This is a snapshot. No action is performed, and later deletion/expiry cannot retract a checklist already displayed or copied.

To reuse an existing profile, choose **Load saved profiles**, then **Review this profile** on the intended record. No profile is automatically selected, even if only one is listed. The API page reads up to 20 owned memories in the exact scope; the screen displays only typed profiles. Ordinary records still count toward the page size and are transmitted to this authorized client. Continue with **Older memory page** when needed. Pages replace the list, include expired profiles and are not a consistent database snapshot. A malformed typed record may be listed but cannot be loaded as a valid form; use the typed API to repair it deliberately.

An expired profile can be reviewed or edited, but cannot build a new checklist. Use the memory manager for expiry changes, renewal or confirmed deletion. Changing a profile preserves its expiry. **Start a new profile** clears the current selection and draft without changing saved records; it does not supersede an older profile automatically.

Editing a selected profile disables planning from that selection until the reviewed replacement is explicitly confirmed and saved, or the original record is reviewed again. The save button explicitly names whether it creates a new record or replaces the selected one. Updates carry the current state fingerprint and fail on conflict rather than overwriting another client's changes.

## Reviewed-state planning

`POST /v1/plans/cleaning` now optionally accepts `expected_profile_revision`, a lowercase 64-character state fingerprint, alongside an explicit `profile_memory_id`. Supplying it without an ID is rejected. Explicit null, malformed values and unknown fields are rejected. The API checks ownership, exact scope and expiry before comparing the fingerprint of the same fetched memory snapshot that supplies the plan. Stale state returns HTTP 409 with no checklist.

The screen always supplies this condition. Older API/CLI callers that omit it retain their prior latest-row behavior. A fingerprint is not a secret, permission grant or monotonic version: identical restored state has the same fingerprint. A concurrent change after the snapshot is read does not revoke that snapshot or the already-built checklist. The API does not hold a write lock for the duration of planning.

## Privacy, failure and resource limits

- Nothing loads, saves or plans on page initialization. No provider, browser speech, training, purchase or robot endpoint is called by this screen.
- User/API changes clear token, private views, selected profile and draft. Token/scope changes clear private views and drafts; a scope change retains the same-account token. Page exit clears the token and state. No local/session browser storage is used.
- The API health capability (`cleaning_planner_protocol: 1` and `memory_management_protocol: 1`) is checked without the token before authenticated calls. This is compatibility negotiation, not proof that a server is trustworthy.
- Requests reject redirects, omit browser cookies and request no-store caching. Streamed JSON is capped at 1 MiB, profile/plan fields are bounded, and responses must match the captured owner/scope/profile state. Displayed strings use `textContent`, not HTML interpretation. IDs must fit JavaScript safe integers.
- Only one operation is pending at a time. Cancellation and context changes invalidate late callbacks. An already-submitted write can still complete. A lost or malformed write response is not retried automatically; reload and inspect actual state before deciding whether to save again. There is no absolute fetch deadline.
- Profile values remain private memory rows. Ordinary chat is a separate path and may recall/transmit them under its existing configured-provider behavior; this screen does not authorize that transmission. Scopes are context filters, not restrictions between clients authorized as the same owner.

The existing [profile limitations](CLEANING_PROFILES.md) still apply: declared surface conditions are not verified; dry methods are not automatically safe; necessary hygiene must not be skipped; no chemical mixtures are proposed; a time budget is not a completion guarantee; sample principles are not Agama quotations. Source review/licensing metadata remains declarations, not independently verified rights or scholarship.

## Verification and what remains unverified

The Node DOM fixtures exercise consent consumption, repeated clicks, dirty-edit planning blocks, explicit selection and paging, identity/destination changes during health/body waits, scope/page-exit clearing, late responses after cancellation, stale revisions, response caps, wrong-owner/scope rejection, and text-only rendering.

Actual streaming Node `fetch` calls to a temporary Python loopback API exercise confirmed profile creation, reload, revision-checked update, checklist output, conflict rejection, expiry and owner isolation. A test reasoner raises if called. Separate engine/API tests check the exact plan snapshot, including a concurrent update by a second engine after reading the row.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_cleaning_planner_ui.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p 'test_cleaning_plan_revision.py' -v
```

The DOM harness is not a real browser. Browser layout, accessibility, CORS enforcement, actual navigation/back-forward caching, mobile behavior, voice and media timing have not been validated here. Real home conditions, cleaning effectiveness, semantic reasoning, model quality and physical safety are not established by these checks.
