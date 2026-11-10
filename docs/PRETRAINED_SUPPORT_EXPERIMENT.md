# Optional pretrained support experiment

This is an offline experiment, not JACE runtime integration, corpus admission,
source authentication, religious qualification, or an authorization to use model
labels in response checking. It imports no optional model dependencies until an
explicit local model directory passes artifact validation. The normal stdlib-only
test environment needs neither PyTorch nor Transformers.

## Frozen baseline

Publisher: [cross-encoder/nli-MiniLM2-L6-H768](https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768/tree/b95119ce93d3e065de6214e38cd4a97b0f2f2c6d),
revision `b95119ce93d3e065de6214e38cd4a97b0f2f2c6d`, publisher-declared Apache-2.0.
Standard `RobertaForSequenceClassification`; no remote custom code. SHA-256 pins
for config, tokenizer, special tokens, model card and safetensors are embedded in
`scripts/predict_pretrained_support.py`. The explicit local directory must contain
exactly these six regular, non-symlink files. Weights SHA-256:
`ec9c5b6a08b60d7a01b465c7ed44b496244dfd1bed3274c95875a74cea89ab35`.
The runner does not acquire weights or install dependencies. Keep weights, private inputs and private predictions outside the repository.
The published fixture and frozen results below contain only original fictional
examples; they do not include a religious or private corpus.

Every complete supplied passage is concatenated in input order, using two newline
characters (`\n\n`) as the separator. No passage IDs or citation text are injected.
This entire premise and the complete claim hypothesis are tokenized as a pair,
with special tokens, no padding and `truncation=False`. Citations are checked for
exact excerpts but never select, shorten or reorder context. Real pair length is
checked before inference: more than 512 tokens causes explicit abstention, never
clipping. Valid input has 1–128 cases and the same field, string and citation
limits as the existing evaluator export. Unknown fields, including gold labels,
rationales and group identifiers, are rejected at every defined object boundary.
The exported canonical input hash is verified. The dataset hash is provenance
metadata, not proof of dataset authorship or correct gold judgments.

The decision is argmax of exactly three finite raw logits:

- Index 0, contradiction: `contradicted`.
- Index 1, entailment: `supported`.
- Index 2, neutral: `not_established`.

An exact tie selects the first class index. There is no threshold, tuning,
calibrated confidence, prompt, retrieval, fallback provider or runtime admission.
Malformed output, nonfinite logits, tokenizer failure and inference failure produce
explicit abstentions. Failure to validate inputs or artifacts fails the entire
command before inference. A tensor/model error never becomes a fabricated class.
Raw logits are retained for valid outcomes, not presented as probabilities.

## Reproduce locally

Use an independently provisioned isolated CPU environment. The prepared experiment
uses Python 3.12.14, PyTorch 2.8.0+cpu, Transformers 4.57.1 and safetensors 0.6.2;
the exact environment-specific lock and official wheel URLs/hashes are recorded in
`evals/pretrained_support_requirements.lock` and
`evals/pretrained_support_wheels.json`. The lock targets CPython 3.12, Linux x86-64,
and is not a portable dependency promise. Model file URLs, sizes and hashes are in
`evals/pretrained_support_model_manifest.json`. Download and verify these artifacts
separately, then install the wheels in an isolated environment with
`--no-index --find-links /outside/repo/wheels --require-hashes --no-deps -r`
followed by that lock path. The lock does not itself fetch the CPU PyTorch index.
Bootstrap pip was 25.0.1; no global packages were installed.
The adapter records actual versions rather than claiming cross-version equivalence.
It forces offline/telemetry-disabled environment flags before optional imports,
`local_files_only=True`, `trust_remote_code=False`, safetensors loading, CPU,
one PyTorch thread, seed zero, deterministic algorithms, `eval()` and
`inference_mode()`. No download fallback exists. This is an application-level
offline policy, not an OS network sandbox. Run in a network-disabled process if
network isolation must be independently enforced. Use a dedicated process and
immutable local artifacts; concurrent file replacement is outside this experiment's
threat model. Bytecode writes can be suppressed with Python's `-B` option.

Generate a strict label-free export with the existing evaluator. Do not pass a
gold dataset to the model runner. Then run either command (stdout only):

```
/path/to/isolated/python -B scripts/predict_pretrained_support.py predict \
  --inputs /private/export.json --model-dir /outside/repo/model
/path/to/isolated/python -B scripts/predict_pretrained_support.py inspect \
  --inputs /private/export.json --model-dir /outside/repo/model
```

`predict` emits exactly the existing scoring prediction schema. `inspect` emits
an inspection envelope with the exact scoring object under `predictions` plus
separate traces, input/dataset hashes, runtime/artifact identity and policy.
Extract that prediction object for scoring to avoid a second inference run.
The runner writes only stdout/stderr and has no output-sidefile options. JSON
output is bounded at 2 MiB. Inspection omits passage/claim text but includes case
IDs and premise hashes, so handle it with the same privacy care as the inputs.

## Validation and limitations

Run the synthetic, stdlib-only boundary tests:

```
python -B -m unittest discover -s tests -p test_pretrained_support_boundary.py -v
```

Tests use only original tiny synthetic examples, not challenge fixtures. They
cover full context, label mapping/ties, token overflow before model invocation,
malformed/nonfinite outputs, backend failure, strict schema/hash/citation checks,
case bounds, lazy import and offline adapter settings. Stub results establish
boundary behavior, not pretrained accuracy or performance. Independent review and
real-model execution are separate steps. Freeze runner/test/document hashes
before viewing any fresh evaluation cases or model predictions. Subsequent changes
must be versioned and disclosed; never silently tune against that evaluation.

A generic NLI model can confidently misread scope, conditions, quantities,
attribution or multiple sources. Concatenated passages do not resolve conflicts
or establish truth. Publisher licensing and reproducibility do not establish
competence. Any score depends on independently reviewed gold judgments and the
specific disclosed test set; no unseen generalization claim follows.

## First frozen experiment, 2026-11-10

**This candidate is not suitable as JACE's semantic-admission gate on the evidence
collected here. No model runtime, source admission, release or deployment changed.**

The unchanged runner and fixed argmax policy were frozen before viewing the fresh
candidate outcomes or gold. The new fixture contains 120 original fictional English
cases: 40 matched triples, five per phenomenon, with 40 supported, 40 contradicted
and 40 not-established labels. Its author used the schema/task contract, without
candidate code, outputs or earlier fixtures. This is a newly authored diagnostic,
not a claim that pretrained training data lacks related patterns or templates.

One complete local CPU model run produced 120 predictions and zero abstentions:

- Correct: **73/120 (60.83%)**.
- Unsupported claims incorrectly called supported: **11/80 (13.75%)**.
- Supported claims recovered: **22/40 (55%)**.
- Entire matched triples correct: **9/40**.
- Gold supported: 22 supported, 12 contradicted, 6 not established.
- Gold contradicted: 6 supported, 30 contradicted, 4 not established.
- Gold not established: 5 supported, 14 contradicted, 21 not established.

Correct counts by phenomenon (15 cases each): attribution 8, conditionals 9,
cross-source 11, location 10, negation 10, quantifiers 11, quantity 8, time 6.
These small, deliberately constructed, dependent groups do not estimate general
English performance. The 120 observations are not 120 independent statistical trials.
No confidence interval, statistical superiority claim or doctrinal claim follows.

Concrete false-support examples include interpreting a closed drawer as locked,
treating an unconfirmed speaker's claim that a well was empty as established fact,
calling an 08:30 visitor earlier than an 08:00 opening, and calling four chipped
cups out of twelve a half. These are observed errors, not evidence that another
candidate or prompting method would repair them.

### Label review and ambiguity

Two separate label-free reviews covered disjoint 60-case halves. Each case had
one independent primary-label review, not two. Primary labels agreed with the
original gold in 120/120 cases. This validates label agreement, not model quality
or expert review. Four cases were flagged as potentially ambiguous:

- `xea6c69a8ca13d5b7`: leaving an inspection to someone else may imply deliberate
  delegation rather than nonparticipation alone.
- `xf53ad7a513770885` and `x29e7ab12109a5987`: earning a ribbon need not imply
  physically receiving it.
- `x10503330bc7b8ce9`: "two" fruitless trees may mean exactly two or at least two.

The original fixture, labels and first model score are preserved. No label was
changed to improve the score. A secondary sensitivity view excludes **all three
complete triples** containing any flagged case, including their unflagged members,
regardless of prediction correctness. That leaves **69/111 correct (62.16%)**,
**10/74 false supported (13.51%)**, **21/37 supported recovered**, and **9/37** wholly
correct triples. It does not replace the 120-case primary result or resolve the
ambiguities. No thresholds, weights, parser or policy were tuned on these outcomes.

### Reproducibility and resource evidence

- `evals/pretrained_support_cases.json`: original cases, gold and rationales.
- `evals/pretrained_support_frozen.json`: byte-exact first inspection envelope,
  including scoring predictions, all raw logits, reasons, token counts and identity.
- `evals/pretrained_support_label_review.json`: primary labels, rationales and flags.
- `evals/pretrained_support_observed.json`: hash bindings, original chronology,
  confusion counts, sensitivity view, resource observations and limitations.

The fixture SHA-256 is
`beb7d4c46bd2f72143030044348094ddd382549ee95bc3d90f663d014ee06334`;
the frozen result SHA-256 is
`75b55e42d59532f14341a09358a3b73c01e25a891956ce814403f3a0cf84d3d0`.
Chronology and hashes bind saved content but do not prove authorship, independent
execution or an absence of training overlap. The challenge is disclosed now and
must be treated as regression/development data in later work.

Observed pair lengths were 44–96 tokens, with no truncation or model error.
The one process took about 13.56 seconds including six-file hashing, loading and
all 120 predictions. Linux reported peak RSS 623,464 KiB (about 609 MiB). This is
one environment-specific batch, not per-case latency or production throughput.
A separate actual-tokenizer control produced 1,211 tokens and abstained before
any model-forward call, confirming that the stored tokenizer's default truncation
was overridden. That boundary control is not another performance observation.

The model publisher declares Apache-2.0 in its card; the pinned revision has no
standalone LICENSE file. This is not an independent audit of training-data rights.
Verified official CPU/PyPI wheels were installed in an isolated environment.
Initial package acquisition may have populated the default pip cache; final
installation and runtime caches were isolated. The run used application-level
offline flags and local-only loading, not an OS-enforced network sandbox. No paid
service, inference API, private source or religious corpus was used.

The ordinary test suite replays saved evidence with the standard library. It does
not download weights or reproduce neural inference. Real inference, independent
label review, boundary tests and arithmetic replay are different forms of evidence
and must not be added together as a larger performance sample.

## Next validation gate

Keep this candidate outside runtime admission. A future candidate must freeze its
policy before a new independently authored challenge, retain its first outcomes,
review labels without model feedback, and report false support alongside coverage.
Any tuning on this published fixture requires a separate unseen evaluation. Better
scores on synthetic English would still not clear source rights, transcription,
citation scope, Jain scholarship, or real-world safety requirements.
