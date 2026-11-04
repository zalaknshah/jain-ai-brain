# Explicit dispute-preparation screen

`web/dispute.html` adds a form for the [stateless dispute worksheet](DISPUTE_PREPARATION.md), linked from the conversation console. It uses only the existing authenticated local API. It does not save a case, retrieve memory or sources, call a model, contact a partner or select an option.

This is repository-local UI work, not a published site. Serve the existing `web` directory through the project's normal local HTTP workflow, use an allowed origin, and connect only to a trusted API. Real browser access was unavailable during this slice; no browser restriction was bypassed.

## Workflow

1. Enter the assigned user, trusted HTTPS or local loopback API origin, and assigned token. The destination cannot contain a path, query, fragment or embedded credentials.
2. Enter the decision, nullable reported positions and separate fact-status groups. Choose all concern flags explicitly. “Not flagged by me” is not an assessment that the situation is safe or free of obligations.
3. Enter two through four complete candidate options. Every fit, reversibility and agreement field starts unselected. A missing position requires unknown fit. Options remain in entered order and are never ranked.
4. Select **Review locally, do not send**. No health request or other network call occurs in this step. The page shows the normalized worksheet and exact API route without displaying the token. Leading/trailing whitespace and blank list lines are removed; review the resulting entries.
5. Check the initially unchecked confirmation for this one worksheet, then choose **Send this worksheet for comparison**. Confirmation is consumed before any network request. The page checks the public protocol endpoint without sending authorization or case data, then submits the captured worksheet once to `/v1/plans/dispute`.
6. Read the report as user-reported declarations and conditional questions, not independently verified facts, mediation or legal advice. No option is recommended. Another request requires a new local review and confirmation.

The page does not silently fill the form from chat, saved memories or a sample case. The API remains responsible for its exact schema and limited harm filter. Client validation is preliminary: JavaScript lowercasing differs from Python Unicode casefold, and compact JSON byte counting differs from the server's normalized serialization. The server may safely reject a locally reviewed near-limit or duplicate input. Nothing is automatically retried.

## Privacy and stale-request handling

Drafts, tokens and reports remain in page memory only; no local/session storage, cookie, URL query or automatic download is used. Changing account, token or destination clears private case fields and reports. A separately retained identity snapshot prevents silent autofill changes from rebinding an older draft or completed report when the user reviews again.

Edits, option insertion/removal, cancellation, and page lifecycle events invalidate review and confirmation, abort pending fetches and suppress stale results. Raw identity and every raw form field/option order are rechecked before submission and at asynchronous response boundaries, including streamed chunks. This also handles changes that do not emit an input event in the script fixtures. `pagehide` and `pageshow` clear tokens, drafts, review and results rather than trusting restored consent.

Cancellation clears this page and stops further local processing. It cannot unsend details already received by an API, proxy or other surrounding software. A trusted API or browser may retain information outside this page's control; there is no system-wide secrecy or erasure guarantee. Do not enter passwords or details that the selected API should not receive.

## Response boundary

Fetches prohibit redirects, omit browser credentials and request no-store handling. Only the captured origin is used. Streaming UTF-8 decoding caps responses at 64 KiB, regardless of the declared Content-Length. Malformed or mismatched responses clear the result and produce a content-free remote error without retrying.

The screen checks the protocol, exact worksheet echo, option order and echoed option content, unanswered questions, user-report attribution, risk status and false/null saving/provider/action/recommendation flags. It renders text through `textContent`, never HTML. A fixed local concern banner preserves the appropriate safety or deadline/commitment warning independently of response prose.

These are structural checks, not proof that the API is honest or that its prose is correct. They do not authenticate a partner, establish agreement, verify allegations, provide semantic safety or qualify legal/business advice. The displayed report says the worksheet echo matches, not that its claims were verified.

## Verification limits

`tests/dispute_preparation_harness.js` runs the actual page script in a simulated DOM. It covers local-only review, consumed consent, repeated clicks, option limits, input changes, silent identity changes before review/during requests, stale streamed bodies, cancellation, page restoration, response tampering, text-only rendering, UTF-8 and byte caps, protocol/network failure and no retry.

`tests/test_dispute_preparation_ui.py` also sends actual JavaScript requests to a synthetic local Python API. It verifies comparison, flagged-deadline behavior, authoritative Unicode duplicate rejection and explicit recovery, with database change counts and a forbidden-provider fixture.

These are script and loopback integration checks. They do not verify real rendering, browser autofill, browser back/forward cache behavior, keyboard/screen-reader usability, mobile layout, or a real browser's privacy/network implementation. No screenshot, real-browser pass, public deployment or production readiness is claimed.
