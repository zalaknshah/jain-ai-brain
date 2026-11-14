# Synthetic supported-intent training probe

This is a bounded CPU classifier-head research result, **not general Jain
reasoning, a trained robot brain, scholarly understanding, or a qualified safety
policy**. Nothing is promoted to JACE runtime or published as model weights.

## Why this increment

The preceding centered six-class head could confuse a demand to fabricate a
scripture quotation with a legitimate provenance question. This experiment adds
an explicit `unsupported` training class and replaces terse examples with longer
original synthetic advisory requests. Both training breadth and class structure
change; improvements cannot be attributed solely to the new class.

The six supported classes are editorial routing labels: noninjury, restraint,
perspectives, conditional claims, provenance, consent. `unsupported` includes
unrelated tasks as well as inappropriate requests. It is not a universal ethical
judgment or exhaustive safety taxonomy. Only class labels are produced. No robot
commands, verse answers, translation outputs or real-world actions are generated.

## Frozen protocol, provenance and independent evaluation

- Immutable MIT-labelled E5 encoder revision:
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Model/dependency metadata lives in the
  adjacent `e5_head_independent` directory. Every local model-file hash is checked
  before encoding; safetensors, offline loading and remote-code disabled are used.
- New original assistant-authored train60rows and dev36rows span EN/HI/GU. Train
  has12 supported and8 unsupported scenario families, each in3 languages. Dev has
  6 supported and6 unsupported families. These are unreviewed synthetic language
  drafts, not scripture, native-speaker validation, personal data or private books.
- The protocol was frozen before holdout authoring at SHA256
  `b8a9086cc92d1c8fe1c6ec350a9bf42006cef265f0d2da51233d4ff9d23521f1`.
  Full data/runner freeze is local commit `63aa1014314b85243761249a612fefb6f84cf48b`.
  Dev output/cutoff checkpoint `3b1ccc74acdf39210525a63cc6e358bd5ed4f7ab` precedes
  heldout release. These local commit references document chronology; they are
  not authenticated external reviewer signatures.
- A different assistant authored and withheld the fresh heldout, blind to NEW
  train/dev examples. It knew earlier experiment outcomes. The authoring note is
  retained unchanged; its historical “freeze pending” statement describes the
  time of authoring, not current state. The set was released only after full
  source/data/dev-result freeze confirmation.
- Fresh heldout hash:
  `5d4184d9b477bfc43c17c3b227819b74129e52f89dbe55723ac19d15ac70bbfd`.
  Its36 rows are **12 matched-language families**, six supported and six
  unsupported, NOT36 independent scenarios. No expert/native-speaker validation
  is claimed. Exact case/text and family cross-split checks pass but cannot prove
  semantic independence or label truth.
- No earlier heldout examples enter new train/dev. Prior failure knowledge did
  motivate this protocol. No threshold or model tuning follows fresh evaluation.

The frozen encoder is mean-centered using TRAIN vectors only, then normalized.
A zero-initialized seven-class softmax head receives400 full-batch updates,
learning rate0.3, L2=.001. Training cross entropy falls1.94591→0.28296 before the
last update. This is genuine classifier-head optimization, not encoder fine-tuning
or generative model training. A top-ranked `unsupported` class always abstains;
other predictions need dev-selected score/margin cutoffs. The fixed dev grid
selects score0/margin0.1. Raw probabilities are not calibrated safety confidence.

## Observed fresh-test results

| Method on the SAME fresh set | Supported correct accepts | Unsupported false accepts | Abstentions |
|---|---:|---:|---:|
| Prior raw six-class head |0/18|0/18|36/36|
| Prior centered six-class head |1/18|0/18|35/36|
| New seven-class head and richer train/dev |11/18|0/18|25/36|

There were0 wrong-supported accepts in all three methods. Prior heads use their
unchanged original train/dev and optimizer; the comparison script was added after
the new run and does not adjust their settings based on test outcomes. It is a
post-run matched-baseline comparison, not a preregistered causal ablation.

New supported acceptance: English4/6, Hindi4/6, Gujarati3/6. All six unsupported
families were rejected in each language. Seven supported examples were refused:
all three versions of one perspectives-family case were classified unsupported;
four other noninjury/restraint examples fell below the margin. These are real
limitations, not “safe and complete” behavior. Zero observed false accepts on six
unsupported families cannot establish real-world reliability or robot safety.
The11/18 accepted result is narrowly encouraging for this synthetic router only.

## Verification and resource limits

Nine focused tests passed. Independent scoring review checked all IDs/labels,
freeze hashes, exact pre-release dev output/cutoff retention and aggregate counts.
Two sequential CPU runs matched all deterministic fields exactly, excluding
elapsed time and RSS. The initial run took about7.49seconds and peaked at808388KiB
RSS with two threads. No GPU, paid resource, remote inference, private corpus,
service, full JACE suite, runtime integration or robot qualification was used.

```
python -m unittest -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
python experiment.py --model-path /path/to/pinned/local/model --heldout
python baseline_compare.py --model-path /path/to/pinned/local/model
```

The adjacent baseline source and metadata are required, so retain the repository
layout. Downloaded encoder weights stay outside the repository; learned head weights
exist only in process memory. No adapter/model export or automatic publication
occurs. Existing
source-rights review and approval holds remain unchanged. This fresh test is now
seen: any further model selection needs another untouched test, not rebranding
this set as independent again. Broader adversarial cases, actual expert language
review and large-scale independent evaluation remain necessary.

No rows were truncated at the128-token encoder limit: maximum token counts were
44(train),44(dev),59(heldout), as recorded in token-lengths.json.
