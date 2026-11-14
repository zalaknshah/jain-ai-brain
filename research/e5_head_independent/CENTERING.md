# Train-only representation centering probe

**Rejected candidate.** This bounded next experiment investigates whether the
frozen multilingual encoder's shared embedding component makes the tiny trained
head's scores too weak. The hypothesis is exploratory, not an established cause.
It does not train a generative model, ingest Jain books, or change JACE runtime.

## Protocol and non-independence disclosure

`centering-protocol.json`, script and tests were frozen in local commit
`15c5ba4e81059c639e3a1526d2c62c345421885a` before this run. Frozen hashes are in
`centering-freeze.sha256`. The only transform change subtracts the mean of the
36 TRAIN embeddings and normalizes each resulting vector. The mean is never fit
on dev or regression data. Near-zero centered vectors fail explicitly. The head,
400-update optimizer and dev-only threshold grid/objective remain unchanged.
No new model files, training rows or private material were acquired. Raw and
centered heads are both fit from scratch; no previous weights are loaded.

The previously independent 36-case set has already been inspected. It is now
**seen regression only**, NOT a fresh independent validation set. This fixed
probe was designed after seeing the earlier failure, even though preprocessing
statistics/thresholds use only train/dev. Neither the source freeze nor unchanged
data hashes restore holdout independence. No claim of a new validated improvement
may be made from these cases. A new model-selection stage requires a newly
independently authored evaluation set after protocol freeze.

## Observed outcome

| Measure | Raw head | Train-centered head |
|---|---:|---:|
| Dev correct-known accepts |14/18|16/18|
| Dev unsupported false accepts |0/9|0/9|
| Seen-regression correct-known accepts |0/18|1/18|
| Seen-regression unsupported false accepts |0/18|1/18|
| Seen-regression wrong-known accepts |0/18|0/18|
| Seen-regression abstentions |36/36|34/36|
| Seen-regression known top1 matches BEFORE abstention |14/18|15/18|

The fixed dev grid selects raw cutoffs probability0.3/margin0.1; centered cutoffs
probability0.5/margin0.3. English and Hindi still accept0/6 supported cases each.
Gujarati accepts1/6 supported cases but also1/6 unsupported cases: a request to
invent a Jain verse and present it as a real quotation is classified as
`provenance`. The supported Gujarati provenance-verification question is the
other accepted case. These are classification outputs; no verse or robot action
was generated. The false accept prevents promotion regardless of better dev
numbers. All languages have6/12 correct decisions including correct abstention,
which is not evidence of useful general Jain reasoning.

## What this tells us, and what it does not

Top1 topic matching is often correct on supported prompts, yet useful accepted
coverage remains poor. A provenance topic match can also occur on a fabrication
demand. This shows why topic similarity alone is insufficient for supported-intent
selection in this small experiment. It does not prove a general model limitation
or validate a safety gate. Lowering thresholds against these known failures would
be tuning on the regression set, not a fresh success.

A distinct next hypothesis is explicit unsupported-intent training using original
negative examples, broader independently written train/dev paraphrases, followed
by another untouched heldout. That proposal is not implemented or validated here.
No existing scholarly/source-rights review requirement is relaxed.

## Reproduction and checks

Ten focused tests pass, including train-only mean fitting, unit-normalized output,
zero-norm refusal, baseline training and false-accept counting. Two sequential
CPU processes reproduce all deterministic fields exactly, excluding runtime/RSS.
The first run takes about5.01seconds and peaks at779996KiB RSS, with two threads.
This is tiny frozen-encoder/head work, not full-model training capacity.

```
python -m unittest test_centering test_experiment -v
sha256sum -c centering-freeze.sha256
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
python centering_probe.py --model-path /path/to/pinned/local/model
```

The parent research README documents the exact MIT-labelled encoder snapshot,
original synthetic data and dependency versions. No weights, corpus, deployment,
service activation, model publication or full JACE application tests are included.
