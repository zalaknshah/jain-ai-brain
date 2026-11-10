# Independent synthetic scoped-support challenge

## Scope and freeze

This is a new, finite challenge for the unchanged standalone scoped-unary
candidate, not a replacement for its contract or the JACE runtime. The
challenge author read only [the contract](SCOPED_SUPPORT_CONTRACT.md), without
reading the candidate, earlier tests, datasets, or outputs. The author froze
151 inputs and explicit expected labels, reasons, and selected trace
assertions before any candidate execution on them.

The [frozen corpus](../evals/scoped_challenge_v1/challenge.json) SHA-256 is
`50e494891717c78756d48ae43948abfd3c70d48277f8611195d583ae6c47b72a`.
The original authoring artifacts and ten prebound batches are included under
`evals/scoped_challenge_v1/`. The publication manifest changes only the
executor-specific contract location to a repository-relative path and adds
its packaging provenance. All files listed in that manifest retain their
original frozen bytes.

There are 48 membership, 34 logic, 24 scope, 23 grammar, 13 bound, six
reference, and three focused diagnostic cases. Proposed expectations include
38 supported, 30 contradicted, 43 not-established, and 40 abstention answers.
These are authored expectations, not measured model results. Template-expanded
cases are correlated. All content is synthetic and no private source is used.

## Portable execution and evidence retention

The new runner invokes both actual CLI operations in fixed batches of 16,
with no retry, automatic rebatching, or tuning. It checks exact prediction
objects, trace bindings, labels, primary reasons, and the selected authored
trace assertions using type-sensitive comparisons. It is **not** a complete
trace-schema validator or a separate implementation of the semantic contract.

It retains the full corpus, every attempted bound input, raw stdout and
stderr for both operations, their sizes and hashes, return codes, and a
summary. A timeout or launch failure stops the campaign and leaves completed
and partial process output intact. A semantic mismatch is retained and does
not change expectations. Existing output directories must be empty so a
later execution cannot overwrite an earlier result.

From the repository root, with Python 3.10 or later:

```sh
python -B scripts/evaluate_scoped_challenge.py \
  --cases evals/scoped_challenge_v1/challenge.json \
  --expected-sha256 50e494891717c78756d48ae43948abfd3c70d48277f8611195d583ae6c47b72a \
  --output-dir /tmp/jace-scoped-challenge-new-run
```

Use a new empty output directory for each explicit run. The runner exits 0
for a matched campaign, 1 for a mismatch or failed candidate request, and 2
for its own invalid setup. It refuses a changed candidate, evaluator,
contract, or corpus binding. The candidate remains byte-identical to public
commit `f33c6afd68b52895f2d9a38bfd70c842df79a5f6`.

The author's additional saved-trace checker can independently check its
selected expectations without invoking the candidate:

```sh
python -B evals/scoped_challenge_v1/check_challenge.py \
  --corpus evals/scoped_challenge_v1/challenge.json \
  /tmp/jace-scoped-challenge-new-run/batch-*.inspect.stdout.json
```

## Claims and limits

The initial checkpoint freezes the portable runner and original challenge;
execution results, when available, are recorded separately. A successful run
would establish only agreement with these explicit finite expectations. It
would not establish ordinary-English understanding, Jain scholarship, source
truth, neural improvement, exhaustive input coverage, a full independent
semantic oracle, corpus admission, or production readiness. Once published,
these cases are disclosed development material, not a reusable hidden test.

The earlier generated development comparison is a separate historical
campaign. Its original runner and full evidence are not bundled here, and
this challenge does not audit, reproduce, or add to its reported case count.
No source acquisition, model inference, package/runtime change, main-branch
integration, deployment, or source-rights admission is part of this work.
