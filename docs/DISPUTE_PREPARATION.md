# Private, explicit dispute preparation

The original business-partner example has an authored chat checklist. This separate feature lets the user enter a specific decision, reported positions, fact-status groups and two to four candidate options, then produces a comparison worksheet. Changed declarations change the worksheet and review questions. It does not decide who is right, select an option, understand motives, mediate a dispute or send anything to a partner.

A [dedicated form and local-review screen](DISPUTE_SCREEN.md) is also available from the console. Its real browser behavior remains unverified.

The builder is stateless. It does not initialize an engine, retrieve sources or memories, call a model, save case details, contact anyone or create a commitment. An API server can already have an engine/database for other routes; this route does not access them. Ordinary chat remains unchanged and does not automatically enter this workflow or extract these fields.

## Local CLI

From a checkout, try the original fictional example:

```sh
PYTHONPATH=src python -m jace.cli prepare-dispute --stdin < examples/dispute_worksheet.json
```

The `--stdin` flag is required. The CLI reads at most 32 KiB plus one overflow-detection byte and rejects excess input. This branch returns before constructing `CognitiveEngine`, even if model, corpus or database environment variables are configured. No case filename or private text is placed in a command-line argument by the tool. Output is printed as JSON; the terminal, shell redirection or other software may retain it. Stateless does not mean a guarantee of secrecy or system-wide erasure.

## Authenticated API

`POST /v1/plans/dispute` requires the existing owner bearer authorization and allowed-origin policy. Its JSON body contains exactly `worksheet`, with an optional `user_id` that must match the authenticated owner. No `learn`, save, model mode or action field is accepted. Health exposes `dispute_preparation_protocol: 1`.

A valid request returns the prepared worksheet with `saved: false`, `provider_called: false`, `action: null`, `actions_executed: false` and `recommended_option: null`. The response is no-store. This stateless route does not wait for the engine lock, but remains subject to ordinary request-byte, read-deadline, connection and peer-rate limits. Validation failures use content-free field errors; entered case text is not included in error messages.

## Exact worksheet fields

All fields below are required, including explicit empty lists or null positions where information is missing. Text is trimmed and single-line, without control/format characters. Case-insensitive Unicode-composed duplicate labels or duplicate fact entries are rejected. The same exact fact entry cannot appear in more than one status group; this check does not detect semantic contradictions.

- `decision`: 1–500 characters describing the decision under discussion.
- `my_position`: 1–500 characters or null when unknown/not supplied.
- `partner_position_reported`: 1–500 characters or null. This is what the user reports, not an independently obtained partner statement.
- `facts`: exactly `reported_agreed`, `disputed`, `unknowns`, each a list of up to eight distinct entries of 1–400 characters. Even “reported agreed” remains a user declaration, not established truth.
- `constraints`: exactly `safety_concern`, `formal_deadline`, `binding_commitment`, each a literal JSON boolean. False means only that the user did not flag that concern. It is not a finding that the situation is safe or free of deadlines/obligations.
- `options`: two through four objects, each containing every field below:
  - `label`: distinct text of 1–60 characters.
  - `description`: 1–600 characters.
  - `my_fit`, `reported_partner_fit`, `reversibility`: each exactly `yes`, `no` or `unknown`, representing the user's assessment. If the corresponding position is null, its fit must remain `unknown`.
  - `agreement`: exactly `not_discussed`, `reported_agreed` or `disputed`. Reported agreement is not current consent or authorization.
  - `open_questions`: up to five distinct entries of 1–400 characters.

The normalized worksheet must fit within 32 KiB of UTF-8 JSON and the full report within 64 KiB. The CLI checks its final pretty-printed UTF-8 output including the newline before writing anything, so formatting overhead can reject a near-limit report that would fit the API’s compact JSON. CLI JSON rejects duplicate keys, nonfinite values and invalid UTF-8. The API also uses its existing strict JSON reader. No option is ranked by the number of positive declarations; output preserves entered order and explicitly has no recommendation.

## What the worksheet does

- Preserves the entered decision, separate positions and fact-status groups without converting a disputed or unknown claim into an agreed fact.
- Asks for missing positions or missing reported agreement on facts, and suggests clarifying disputed claims/unknowns without assuming their truth.
- Adds option-specific review prompts based on declared fit, reversibility and agreement, while keeping supplied open questions visible.
- For a flagged safety/coercion concern, pauses ordinary negotiation or joint-meeting suggestions and points to a safe setting and appropriate qualified support. It does not propose contacting anyone to verify consent.
- For a flagged formal deadline or binding commitment, calls for appropriately qualified review. It never says preparing the worksheet extends a deadline, preserves rights or approves a contract.
- Any flagged concern suppresses ordinary reversible-trial prompts. The options remain unselected material for review, not instructions to implement.

Every free-text field separately passes through the existing limited English harm-pattern filter. A prevention phrase in one field cannot exempt a harmful phrase in another. The filter may reject a benign report of past harm or miss harmful meanings; no numeric ethics scores or “low risk” assessment are presented. There is no semantic safety, legal, financial, scholarly or interpersonal accuracy qualification.

## Evidence and remaining work

`tests/test_dispute_preparation.py` covers changed inputs, unknown positions, disputed/claimed agreement, option ordering, all risk-flag combinations, nested-field screening, exact schemas, Unicode/byte limits, private errors, authenticated API behavior, no engine/provider/memory access, and CLI execution with intentionally unusable model/corpus configuration. Tests use original fictional data and local loopback HTTP only.

The workflow provides a local builder, CLI, API and separately tested review screen. It adds no real-browser qualification, source corpus, trained reasoning, partner communication, saved dispute history or external integration. The example is not legal or business advice and should not be treated as a real agreement.
