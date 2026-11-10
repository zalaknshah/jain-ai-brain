# Contrastive claim-support evaluation

This is a separate offline evaluation boundary, **not a semantic-support model**.
It scores explicit supplied predictions against an original-fiction challenge.
It does not generate predictions, call providers, train a model, admit source
text, modify JACE runtime behavior or establish Jain doctrinal competence.

The existing [14-case diagnostic](SEMANTIC_SUPPORT_DIAGNOSTIC.md) exposes why an
exact citation match is not entailment. The new challenge keeps each group's
passages and exact citations constant while changing only the claim. Citation
validity therefore cannot distinguish the three semantic labels.

## Challenge and labels

`evals/claim_support_cases.json` contains 48 newly authored fictional cases:
eight phenomena, two fictional settings per phenomenon, three matched claims
per setting. The phenomena are negation, quantity, quantifiers, time, location,
conditionals, attribution and cross-source joins. No collected religious text,
private data or historical translations are included.

The labels mean:

- `supported`: the complete supplied passages establish the claim.
- `contradicted`: the passages establish an incompatible fact or negation.
- `not_established`: the passages establish neither the claim nor its negation.
  Missing facts are not assumed false.
- `abstain`: a candidate explicitly supplies no semantic class prediction.
  This is a prediction outcome, never a gold label.

Labels and rationales are author/reviewer judgments about fictional evidence.
They are not produced by JACE's citation matcher. The evaluator's initial
implementation and scoring contract were frozen before challenge content was reviewed. A separate review assessed all 48 exported evidence/claim pairs without author
labels. Initial primary labels agreed, but six cases in three groups had wording
ambiguities. All nine records in those groups were clarified consistently and
re-reviewed; no labels changed, and no ambiguity flags remained. This was fixture
review, not a 48/48 runtime-model score. The final dataset SHA256 is
`56791ccb519cd90fa8b615c40bb3b3aa17094b4fb702c37f594328c5742c4a31`.
The only post-freeze evaluator change was a friendly fail-closed error when the
platform lacks nonblocking file inspection; schema and scoring stayed unchanged. This process reviews fixture clarity; it is **not** a
blind evaluation of a new runtime semantic model. Once published, all cases and
labels are disclosed regression data and must not be called unseen holdouts.

## Run locally

Run from the repository root using Python 3.10+ on a platform with POSIX-style
nonblocking file inspection (verified here on Linux). Unsupported platforms fail
closed with an input error; Windows execution is not qualified. Redirect output only to local
files you intend to create or replace:

```sh
python scripts/evaluate_claim_support.py export > candidate-inputs.json
python scripts/evaluate_claim_support.py baseline --baseline abstain > abstain.json
python scripts/evaluate_claim_support.py baseline --baseline supported > supported.json
python scripts/evaluate_claim_support.py score --predictions abstain.json > abstain-report.json
python scripts/evaluate_claim_support.py score --predictions supported.json > supported-report.json
```

Use `--cases path/to/cases.json` on each command for another reviewed challenge.
This is a repository-only script and fixture bundle, not a new installed `jace`
command or wheel component. The script itself writes only stdout/stderr. It imports no JACE runtime, loads
no candidate code and invokes no models or network services. Files are bounded
regular UTF-8 JSON. Duplicate keys, non-finite values, invalid schemas, malformed
citations and unbalanced matched triples fail before scoring. Invalid input
returns exit code 2 and no score report.

Candidate exports contain only case IDs, passages, claims and citations, plus
protocol and data hashes. Gold labels, rationales, group IDs, phenomenon and
scope are omitted. Export order is based on an ID hash, not author insertion
order. This prevents accidental field leakage, not deliberate access to the
public gold file, inferential shortcuts, shared-model contamination or cheating.

## Prediction contract

Supply an inert JSON file containing exactly:

```json
{
  "protocol": 1,
  "input_sha256": "the exact value from the candidate export",
  "predictions": [
    {"case_id": "the exported case ID", "label": "abstain"}
  ]
}
```

The illustration omits the other cases. A real file must contain exactly one
prediction for **every** exported case. Missing, extra, duplicate or unknown IDs
are errors, not implicit abstentions. Unknown labels, extra fields, stale hashes
and gold-label fields are rejected. No confidence field is accepted. Reordering
predictions is allowed because IDs bind them to cases. Changing any raw dataset
byte changes the dataset and exported-input binding, including label/rationale
changes. Hashes do not prove candidate execution, identity or independence.

## Read the results

Reports preserve all original cases, gold labels, rationales, predictions and
per-case correctness. Aggregate reporting separates:

- Mechanical citation validity, which the dataset validator checks separately.
- Semantic prediction count and coverage.
- Three gold classes by four prediction outcomes, including abstention.
- Accuracy among non-abstained predictions, or **null at zero coverage**.
- Correct fraction across all cases and supported-claim recall.
- Unsupported claims wrongly marked supported, with the unsupported denominator.
- Complete matched triples correctly classified. One wrong or abstained member
  makes the whole group unsuccessful.

Always-abstain has zero coverage, zero correct predictions, zero supported
recall, no complete triples and null conditional accuracy. Its zero false-support
count is not reasoning accuracy. Always-supported has full coverage but only
16/48 correct, mislabels all 32 unsupported cases as supported, and completes no
matched triple. These are deliberately weak scoring controls, not model results.

Current JACE's mechanical matcher supplies no three-way semantic prediction.
Representing that absence as `abstain` for scoring must not be described as JACE
refusing to answer each claim: its existing answer/citation boundary can still
mechanically accept unsupported claims. Evidence-only passage display and the
unevaluated seven-question scaffold are likewise not semantic predictions.

## Limits and next step

Passing schema tests or agreeing with these exposed labels does not establish
general semantic ability. A future candidate needs frozen predictions from
label-free inputs, independent source review, genuinely unseen data, broader
languages/domains, adversarial checks and an explicit decision about runtime
use. This evaluator grants no publication, corpus admission or deployment
approval and changes no such boundaries.

A separate [controlled-English unary-logic candidate](CONTROLLED_SUPPORT_CANDIDATE.md)
now exercises this prediction contract through bounded model checking. It is an
offline experiment over an exact grammar, not a change to JACE's runtime citation
matcher or a trained natural-language model. Broader-language coverage and fresh
in-fragment evaluation must be reported separately.
