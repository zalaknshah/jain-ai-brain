# Grounded training candidate alignment audit

Research-only infrastructure, not another model benchmark or admission gate.
The rejected Qwen screen demonstrated that valid JSON did not imply a grounded
answer. Source-lead research also identified an external extraction pattern with
chunk IDs rather than edition/span locators and LLM confidence rather than human
review. No external extraction rows or private literature are copied here.

`audit.py` diagnoses explicitly supplied in-memory candidate/source mappings.
It checks whole-source SHA-256 identity, edition and acquisition declarations,
UTF-8 byte spans, exact raw excerpts, and original/translation lineage. A changed
normalization candidate stays separate from the raw excerpt. Missing edition-
specific rights or translation review references remain flags even if a caller
supplies an aggregate dataset licence or high extraction-confidence score.

This is preparation for building grounded training datasets, not training itself.
It is deliberately **not connected** to `jace.training`, private review exports,
runtime decisions or robot commands. Every result has `training_admitted=false`.
An `exact_span_only` result establishes only byte alignment, never the truth of
an extracted claim or whether the quotation supports it. A deliberate false-claim
test demonstrates this distinction. References and declarations cannot prove
rights scope, acquisition legality, reviewer identity, expertise or translation
fidelity. Existing training admission and actual scholarly/rights review remain
required and unchanged. No genuine source has been admitted by this work.

The API performs no file or network IO, exports no training pairs, and does not
load a model. Reports contain IDs and diagnostics, not source/claim strings;
IDs themselves are caller-supplied and must not contain sensitive information.
It is not a sandbox, authorization mechanism or adversarial security boundary.
At most 32 source entries and 512 candidates are accepted; referenced source
bytes exceeding 1 MiB are flagged. Unreferenced source values are not inspected. Inputs
are caller-held bytes, so the caller must enforce acquisition/read permissions.
No input mutations or normalization are performed.

Run from this directory:

```sh
python -m unittest -v
```

Observed: 27 unit checks passed on original synthetic fixtures. This is component
validation only, not corpus, multilingual model or doctrinal quality validation.
The fixture's Gujarati token is a byte-boundary test, not a translation lesson.
No weights, private texts, dataset rows from third parties, training run, paid
service or deployment are included. Next useful integration is a human-reviewed
edition-linked source adapter, once appropriate rights and scholarly review exist;
this helper must not be substituted for those decisions.

## Review-target binding diagnostic

Structurally aligned rows receive a versioned SHA-256 fingerprint of the exact
source bytes, selected edition/acquisition/rights declarations, byte span, raw
excerpt, claim, target language, translation origin/translator/rights declaration
and optional normalization candidate. A caller may supply that earlier digest as
`review_binding_sha256`; missing or mismatched digests produce review flags. This
makes changes to a previously reviewed target visible without treating arbitrary
review-reference strings as evidence that the current target was reviewed.

Review-reference strings and candidate IDs are not included in the target digest.
Adding a review note does not change the target. This is **not a signature**: a
caller can compute a new digest without a review, and an exact digest never proves
identity, expertise, rights or semantic entailment. Every admission/verification
boolean remains false. Rows with structural errors receive no target binding. Only declared
schema fields participate; unknown extension fields are not covered. Fingerprints
can reveal equality and permit guessing attacks, so they are not anonymization.
Eleven additional synthetic checks cover stale claim, edition, rights declaration,
normalization and translator metadata, plus surrogate-safe canonical ordering and unchanged
review-note targets. No genuine literature or reviewer record is processed.
