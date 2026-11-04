# Explicit cleaning preferences that affect a local plan

The research brief gives the example “we shouldn't wipe down the wooden furniture with water.” Ordinary conversation memories are still free-form text; JACE does not claim to understand that sentence or extract a reliable constraint from it. This feature instead lets the user explicitly save four typed choices and apply them in a dedicated local routine-cleaning checklist.

It is a bounded practical feature, not model training, semantic memory resolution, a complete household planner, a religious ruling or a robot controller.

The [dedicated browser screen](CLEANING_PLANNER_SCREEN.md) provides explicit creation, review, editing and planning. The memory manager still handles expiry and deletion.

## Choices

Every profile must contain exactly these fields:

| Field | Allowed values |
| --- | --- |
| `surface` | `wooden_furniture`, `hard_floor`, `general` |
| `water_policy` | `avoid`, `follow_surface_guidance` |
| `time_budget_minutes` | Integer 1–120, not a boolean or fraction |
| `supplies_policy` | `existing_only`, `review_missing` |

`avoid` keeps both water and liquid cleaning products out of this checklist. It does not assert that dry rubbing or brushing is safe. `follow_surface_guidance` does not certify water or a product as suitable. Surface/product instructions and necessary hygiene take precedence: if they conflict with the requested restriction, the plan says to pause rather than silently relax the restriction or skip hygiene.

`existing_only` pauses when appropriate already-owned supplies are unavailable. `review_missing` permits a list of needed items for review, not an order or purchase authorization. The time value is the user's session budget, including inspection, not an estimate or guarantee of completion. All variants require inspection, appropriate surface/product instructions, no mixing of cleaning products, and pausing for contamination/disinfection concerns or uncertainty. The system cannot inspect the actual surface, organisms or cleanliness.

## CLI workflow

The CLI is a trusted local-operator interface, not an authentication boundary. First preview the exact choices without saving:

```sh
jace save-cleaning-profile local-user --memory-scope home \
  --surface wooden_furniture --water-policy avoid \
  --time-budget-minutes 10 --supplies-policy existing_only
```

After reviewing them, repeat the command with `--confirm-save`. It returns the owned memory ID and state fingerprint. An optional `--expires-at` takes an explicit timezone timestamp. Choices are persisted for later dedicated planning only after confirmation.

```sh
jace plan-cleaning local-user --memory-scope home
```

With exactly one eligible profile, the result includes its ID/revision, applied choices, authored conditional steps, source-grounding qualifications and `actions_executed: false`. With none, the status is `needs_profile`. With several, it is `choose_profile` with no steps. Review the listed profiles and repeat with `--profile-memory-id` to select one explicitly; the system never guesses that the newest declaration overrides an older one.

To replace choices, use `update-cleaning-profile USER MEMORY_ID` with all four choice flags, the currently reviewed `--expected-revision`, and `--confirm-save`. Without confirmation it only previews the proposed choices. The revision is a state fingerprint, not a secret or monotonic version. A changed record causes a conflict instead of overwrite. Updating a profile preserves its owner, scope and expiry.

Expiry and deletion use the existing memory lifecycle commands. The memory-management page displays typed profiles and supports their expiry and confirmed deletion, but disables plain-text editing. Use the typed CLI/API or dedicated planner screen to change choices; this prevents an accidental free-form edit from becoming a planning instruction.

The three dedicated profile CLI commands explicitly use `LocalReasoner` and do not initialize a configured HTTP model adapter. The dedicated plan builder never calls a model.

## Authenticated API

The existing bearer token's owner remains authoritative. Unknown fields, aliases, malformed choices and non-boolean confirmation values are rejected.

- `POST /v1/cleaning-profiles`: exact `profile` object plus `confirm_save: true`; optional `memory_scope` and `expires_at`. Returns the saved typed memory.
- `PATCH /v1/cleaning-profiles`: `memory_id`, complete `profile`, exact `expected_revision`, and `confirm_save: true`. The ownership/revision check and memory/graph/audit change share one writer-reserved transaction. Stale updates return 409; another owner's ID returns 404. Generic memory text correction cannot edit a typed profile.
- `POST /v1/plans/cleaning`: optional `memory_scope`, `profile_memory_id` and `expected_profile_revision`. The optional revision requires an explicit ID and rejects a changed profile with HTTP 409; the browser screen always supplies it. Omit the ID for the explicit one-profile/none/multiple behavior. Explicit null IDs and invalid integer IDs are rejected. This operation only builds a checklist; it does not persist learning, make purchases, call a provider or actuate anything.

Example save body:

```json
{
  "memory_scope": "home",
  "confirm_save": true,
  "profile": {
    "surface": "wooden_furniture",
    "water_policy": "avoid",
    "time_budget_minutes": 10,
    "supplies_policy": "existing_only"
  }
}
```

Only records created with the exact typed `cleaning_profile_v1` source participate. Copying profile-looking JSON into an ordinary memory does not promote it. Stored schemas are validated again at planning time. A malformed active candidate stops default selection instead of being silently skipped; an explicit typed replacement can repair it. More than 25 active candidates require an explicit ID. Default discovery also retains the existing per-scan row/text budgets, not a process/SQL time guarantee.

## Privacy and scope limits

Profiles are still ordinary private memory rows, protected by the existing owner/scope access controls, expiry selection, revision checks and atomic deletion. Scopes do not limit other clients authorized as the same owner. The source field is an application convention, not cryptographic provenance; a trusted local operator with database access can alter records.

The dedicated cleaning-plan path never calls a provider. **Ordinary `think`/chat remains separate:** a profile may enter normal scoped recall like another memory and may be sent to an operator-configured model under that path's existing context-sharing behavior. This feature does not newly authorize such sharing and does not guarantee that an HTTP model or generic fixed chat plan applies these constraints. Use `plan-cleaning` or `/v1/plans/cleaning` for the checked typed behavior. No real provider call was exercised.

Expiry/deletion affect later plan selection, not an already-built checklist, a client-side copy, a provider's retained data or an in-flight snapshot. An explicit expired/deleted/wrong-scope profile cannot be used in a new plan. Existing deletion's separate consent for all unattributed owner audit entries still applies.

Source references are copied through the existing qualified grounding formatter. Built-in principle records remain unverified samples, not Agama quotations. Profile values and generated checklists are not sacred-text interpretations, scholarly findings or professionally qualified cleaning instructions.

## Verification

Tests exercise strict schema and explicit consent, real persisted reuse and changed plan branches, all allowed choice combinations, owner/scope isolation, expiry/deletion, missing/conflicting/malformed profiles, stale and concurrent updates, graph-failure rollback, plain-memory rejection and the offline CLI/API. Browser-script tests also verify that typed profiles cannot be edited as generic text while expiry remains available.

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_cleaning_profiles.py -v
```

Tests use original synthetic records and temporary databases. They do not verify a real home, cleaning effectiveness, general natural-language interpretation, complete Jain reasoning or physical safety. No model weights, collected religious sources or unreviewed materials are admitted by this feature.
