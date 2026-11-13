# Private Prakrit training review

This opt-in local workflow prepares human review and exports approved training
examples from explicitly supplied UTF-8 Prakrit editions and Gujarati (`gu`),
Hindi (`hi`) or English (`en`) translations. It does not acquire books, OCR PDFs,
translate text, invoke a provider, train a model or release anything. Tests use
invented labels and reviewer declarations, not real books or translations.

Rights and scholarly review remain human responsibilities. A licence string,
reviewer name, qualification checkbox or hash cannot prove permission, authentic
editions, reviewer identity, competence, translation fidelity or doctrinal truth.
Reviewers must actually inspect the edition, applicable rights evidence and each
example. Repository access and local-retrieval approval do not authorize training.

## Private files and platforms

Run in an authorized Linux environment with the existing descriptor-relative
no-follow source IO and atomic no-overwrite publication support. Native Windows
preparation/export fails before private reads; there is no unsafe fallback. WSL
Linux is usable when its filesystem supports the required primitives. Keep every
plan, book, draft, decision report and export outside the checkout, build context,
package data and public assets. Do not commit private review outputs.

**Preparation and export retain WHOLE books, including unapproved passages.**
Export embeds their exact UTF-8 text in its private manifest so the training
consumer can independently recompute hashes and byte spans without mutable
external source paths. Only approved example rows enter the worker's optimization
and held-out evaluation lists. This is not a redacted source export. Obtain
permission for whole-file retention before preparation. No sharing or provider
transmission is performed or authorized. Inspection prints private material to
stdout; terminals and redirects can retain it.

## Prepare a review plan

Use `python -m jace.training_review_cli` with `PYTHONPATH=src` from a checkout,
or an installed package. Supply an operator-created JSON plan with exactly
`books` and `records`. No current source-study flags are promoted to training
approval, and no rights decision is inferred from a licence name.

`books` maps each expected lowercase SHA-256 of the whole original file to:

| Field | Required content |
| --- | --- |
| `path` | Explicit absolute, non-symlink UTF-8 `.txt` file |
| `work`, `edition`, `source` | Exact work, edition and acquisition/citation identity |
| `language` | Explicit `pra`, `pra-Deva` or `pra-Latn` declaration |
| `license`, `attribution` | Applicable edition licence and attribution/change notices |
| `rights_evidence` | Reference to the edition-specific permission or rights evidence to inspect |

`records` maps each unique example ID to the following exact fields:

| Field | Required content |
| --- | --- |
| `row` | Exactly `id`, `instruction`, `response`; ID must equal the map key |
| `split` | `train` or `evaluation`, assigned before review |
| `book_sha256` | Original book's exact declared digest |
| `start`, `end` | Integer UTF-8 byte offsets, half-open `[start, end)` |
| `source_text` | Exact decoded source span, preserving bytes through UTF-8 |
| `target_language` | Original book language, or `gu`, `hi`, `en` for a translation |
| `origin` | `original`, `human_translation` or `machine_translation` |
| `translator` | Actual translator/tool and provenance declaration for translations |
| `translation_license`, `translation_attribution` | Translation-specific licence and attribution/change notices |
| `translation_rights_evidence` | Translation-specific rights evidence reference |

For `original` records, the response must equal the exact original span and all
four translation metadata fields must be empty strings. Translated responses
retain their actual origin after human review: a reviewed machine draft remains
`machine_translation` with a separate approved human translation decision.
Instruction and response, split, source span, translator and all rights metadata
are bound by the review revision. Language declarations receive syntax/category
checks only, not automated language identification.

Every book must be referenced. Limits: 32 books, 1 MiB per book, 8 MiB aggregate
original bytes, 512 examples total, 256 per admitted split, 4096 characters per
instruction/response/excerpt, 2 MiB per split, 16 MiB per JSON workflow file or
schema-3 manifest. JSON escaping can hit the manifest limit before the source
byte budget. UTF-8 cuts, mismatched excerpts, duplicate keys and unknown fields
fail closed. Overlapping source spans, including translated variants, cannot
cross train/evaluation splits. Non-overlapping passages from one book are
allowed in different splits; this is not a held-out-book evaluation. Semantic
leakage and duplicated passages in different editions are not detected.

```sh
python -m jace.training_review_cli prepare \
  --plan /private/operator-plan.json --output /private/review-draft \
  --confirm-copy
python -m jace.training_review_cli inspect --file /private/review-draft/draft.json
python -m jace.training_review_cli inspect --file /private/review-draft/decisions.json
```

Preparation pins the expected whole-book hashes and exact spans, then publishes
a private `draft.json` and `decisions.json`. All decisions begin `pending` with
empty reviewer/evidence fields. The draft is rejected by the training consumer.
Review files have mode 0600 in a 0700 directory. Existing destinations, symlink
paths and failed atomic publication are rejected without overwriting outputs.

## Conduct explicit human review

Edit only `decisions.json` in a private local editor after examining `draft.json`
and actual rights evidence. Preserve its format, policy, draft revision, complete
book/example coverage and each unit's revision. Each decision is `pending`,
`rejected` or `approved`. Approval requires nonempty `reviewer` and `evidence`
fields describing the human reviewer and evidence/rationale. These strings are
declarations and evidence references; the workflow does not authenticate or
retrieve them.

- Each book needs an approved `rights` decision covering exactly these scopes:
  `local_retention`, `training`, `evaluation`, `derivative_weights`.
- Each example separately needs approved `rights` with the same scopes. For
  translations this includes the translation's rights and compatibility with
  the original edition. No blanket software licence is applied to source text.
- Each example needs approved `content` with `qualified: true`, declaring actual
  qualified human review of the original excerpt, instruction and response.
- Each translated example additionally needs approved `translation` with
  `qualified: true`, declaring qualified review against the exact original in
  that target language. Original-text rows do not need a translation decision;
  leave it pending. Machine drafts cannot pass without this human decision.

Do not mechanically fill approvals from this list. Insufficient rights, unclear
edition identity, unresolved quotation attribution, unsupported qualifications
or doubtful translation should stay pending or be rejected. Approving one role
does not approve the others. Rights scopes do not authorize remote transmission,
distribution of source text or release of weights.

If text, instructions, attribution, rights metadata or split assignments change,
prepare a new draft and conduct review again. Edited revision strings are not a
substitute for review. Book reviews bind every original byte and metadata field;
example reviews also bind the associated book revision. Export checks the full
draft revision and exact report coverage before selecting anything.

## Export approved examples and run preflight

```sh
python -m jace.training_review_cli export \
  --draft /private/review-draft/draft.json \
  --decisions /private/review-draft/decisions.json \
  --output /private/training-input \
  --confirm-export --declare-no-personal-data
python -m jace.training_cli /private/training-input/train.jsonl \
  --evaluation /private/training-input/evaluation.jsonl \
  --dataset-manifest /private/training-input/manifest.json \
  --model /private/approved-local-small-llama \
  --model-manifest /private/approved-model-manifest.json
```

Export writes only fully approved examples to `train.jsonl`, `evaluation.jsonl`
and schema-3 `manifest.json`, with the original per-unit human decision receipts
and referenced whole books. Pending/rejected examples and their translation text
are omitted from the example inventory. Unapproved original passages still exist
inside retained whole books as described above. Both splits need approved rows;
otherwise no output is published. Duplicate IDs/normalized prompts and normal
training budgets are checked before publication. Export starts no training.

The existing training consumer verifies the hashes, original spans, exact rows,
rights scopes, qualified-review declarations and revisions at preflight, inside
the private worker snapshot and again before marking a run complete. A changed
source, translation, instruction or review state blocks admission/publication.
Preflight does not import ML dependencies or instantiate a model. Actual training
still requires the separate explicit run command and a qualified local backend;
no model execution was qualified by this feature.

Schema 2 synthetic admission remains supported. Schema 3 accepts only these
explicitly reviewed Prakrit examples; other corpora and private memory exports
remain unsupported. A source-review runtime bundle, source-study preparation or
translation-preparation draft alone is insufficient.

Review receipts are editable offline declarations, not signatures or an access
control service. The export is a snapshot: changing the earlier draft report
does not revoke an already exported copy. Withdraw that copy from use, update
its admitted review states or prepare a new reviewed export. There is no central
revocation service, expiry, authentication, secure erasure or automatic policy
upgrade. The exported `draft_revision` is an origin reference; its full-draft
binding is checked at export, while admission recomputes the retained per-book
and per-example revisions. Historical unexported examples are not reintroduced.

No real edition or translation has been rights-cleared or scholarly-qualified by
the synthetic tests. Actual qualified human rights/content/translation review
remains required before a real book or translation can be admitted responsibly.

## Verification checkpoint (2026-11-13)

Under WSL Ubuntu/Python 3.14.4, the 15 new review tests and 30 existing training
tests passed. Full discovery using repository line endings ran 835 tests: OK,
270 skipped. All eight evaluation cases passed. Existing SQLite resource
warnings remained; skipped optional/platform checks are not qualification.
The first aggregate exposed the missing explicit container allowlist entries
for the two new code modules; these were added and the complete suite rerun.
No Docker build/deployment was performed or qualified.

Native Windows/Python 3.10 passed all 13 prior provenance tests and the new
unsupported-platform guard; 14 Linux workflow tests were skipped there.
Synthetic tests cover positive CLI export/preflight, exact original hashes and
UTF-8 spans, pending/rejected/missing/stale decisions, training-specific rights
scopes, qualified translation review, leakage checks, private publication and
no-overwrite/cleanup failures. Worker success and review withdrawal use mocked
backend/export verification with inert fixture bytes, never model execution.
The separate existing capped-worker negative test only checks missing optional
dependencies. No real source rights, translation quality or model behavior was
qualified by this checkpoint.
