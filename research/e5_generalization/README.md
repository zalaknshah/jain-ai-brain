# Broader frozen-model generalization screen

**The previous classifier does not generalize reliably enough for use.** This is
new evaluation evidence for the unchanged synthetic seven-class intent head from
`d40d8afef23e15baf73c36523ebabd9dd3dad824`, not an improved model or release.
It provides neither general Jain reasoning nor a robot safety policy.

## Why and what stayed fixed

The earlier fresh test had only12 translated scenario families. This screen adds
24 new families with more diverse contexts, quoted/negated requests and adversarial
wording. No training examples, development examples, hyperparameters, calibration
rules or previous test files change. No private texts or doctrinal translations
are used. The six supported labels remain editorial advisory-routing categories,
not an exhaustive theory of Jain ethics.

The original60-row train/36-row dev, frozen MIT-labelled E5 encoder and400-update
head are reconstructed using their unchanged source and hashes. TRAIN vectors
alone define centering. The runner asserts exact equality with the prior dev
predictions and frozen cutoff probability0/margin0.1. A top-ranked unsupported
class always abstains. Model-file hashes are checked before local offline loading.
The report includes the reconstructed head and training-mean digests. No learned
weights are exported and no external inference service is called.

Protocol and evaluator were frozen before test release at local commit
`679fdfe60b55f6ef1260c817b42f2b301720e069`, protocol SHA256
`e1a25d2e62727c4d5860f3f10e6b597ff691d49b156ff4b71330357253997fb1`.
A separate assistant authored the fresh examples without reading train/dev or old
heldout files during this assignment. It knew prior outcomes and had authored
prior tests; it is therefore not wholly experiment-naive. Its original authoring
note is retained. These are unreviewed machine-authored language drafts, not
native-speaker or scholarly validation.

The heldout SHA256 is
`0958a6d213d69cfe6aef54e300a8aaf1e0882a12bc17a8914828d834b95412ec`.
Its72 rows represent **24 families**, each in English, Hindi and Gujarati:12
supported families(two per class) and12 unsupported families. Translations are
correlated;72 is not the count of independent scenarios. Exact ID/text/family
collision checks with training, dev and both prior tests pass. They do not prove
semantic independence or label correctness. This set is now seen and must not be
reused as an untouched test after further model selection.

## Observed outcome

| Language | Supported accepted correctly | Unsupported false accepts | Total abstentions |
|---|---:|---:|---:|
| English |1/12|0/12|23/24|
| Hindi |6/12|0/12|18/24|
| Gujarati |7/12|0/12|17/24|
| All translated rows |14/36|0/36|58/72|

There were0 wrong-supported accepts, but **22/36 supported requests were refused**.
Only1/12 supported families was accepted correctly in all three languages. All12
unsupported families were rejected across their translations. Zero observed false
accepts on12 synthetic unsupported families is not a safety guarantee. The earlier
11/18 accepted result from a smaller/different set must not be extrapolated to
broad multilingual competence. These small, unreviewed translations do not justify
claiming Gujarati/Hindi superiority over English.

The English failures include ordinary supported requests about balancing library
staff/student viewpoints, qualifying uncertain manuscript dates, separating an
original passage from a translator's note and requesting voice-recording consent.
A safe quoted-retaliation request also abstains. These are real coverage failures,
not evidence that every refusal is ethically correct. Scores alone do not explain
why any example failed. No harmful act, quotation or robot command is generated;
only the classification decision is measured.

## Verification and reproduction

Six new structural tests passed. Independent review recomputed all72 prediction
labels and counts, verified source/test hashes and family aggregates, and checked
that train-only fitting and dev equality remain intact. A second sequential CPU
process reproduces all deterministic outputs, excluding elapsed time and RSS.
The first run took about8.19seconds with829924KiB peak RSS and two CPU threads.
No test input exceeded128 tokens(maximum62), so no row was truncated.

```
python -m unittest -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
python evaluate_frozen.py --model-path /path/to/pinned/local/model
```

Preserve sibling research directories: they contain the unchanged input hashes,
source and model/dependency manifests. No full JACE application suite, Windows
qualification, live robot trial, learned-model publication, runtime promotion or
private-source rights admission occurred. The new evidence argues for broader
contrastive data and genuine semantic reasoning evaluation with qualified human
review, not lowering thresholds against these now-known failures or claiming
that a toy routing classifier is the requested Jain brain.
