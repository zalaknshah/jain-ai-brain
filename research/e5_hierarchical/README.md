# Two-stage intent/topic architecture probe

**Rejected candidate: useful coverage became worse.** This bounded experiment
separates supported-intent detection from topic selection. It is not a Jain brain,
robot policy, source-knowledge model, or newly validated production improvement.

## Hypothesis and frozen design

The prior seven-class classifier often ranked `unsupported` above a legitimate
supported topic. This probe tests whether separating that competition helps:

1. A binary softmax gate trains on all60 original synthetic examples, predicting
   unsupported versus supported intent.
2. A six-topic softmax head trains only on the36 supported examples.
3. Both heads use the same frozen MIT-labelled multilingual E5 encoder, train-only
   mean centering and normalization. Each zero-initialized head receives400
   full-batch gradient-descent updates, learning rate0.3 and L2=.001.
4. A fixed joint dev-only grid selects gate confidence, topic confidence and
   topic margin, prioritizing false accepts before supported coverage. No test
   values enter training, centering, gradient updates or cutoff selection.

No new train/dev data or private texts are used. The original60-row training and
36-row development datasets, model file hashes and prior source are checked.
Their synthetic/unreviewed-language limitations remain. The binary gate is learned
classification, not authenticated authorization or a safety proof.

Protocol/source freeze is local commit
`2f105527d94ade9f1360431c492ff57566a80c72`, before this run. The architecture was
chosen AFTER inspecting earlier failures. The72-case/24-family set is therefore
**seen architectural regression**, not fresh independent validation. Keeping its
bytes unchanged does not restore independence. No new blind test was consumed
because this candidate already performed worse on dev and seen regression.

## Result

| Metric | Previous seven-class head | Two-stage candidate |
|---|---:|---:|
| Dev supported accepted correctly |12/18|8/18|
| Dev unsupported false accepts |0/18|0/18|
| Seen-regression supported accepted correctly |14/36|7/36|
| Seen-regression unsupported false accepts |0/36|0/36|
| Seen-regression abstentions |58/72|65/72|

No wrong-supported accepts occurred. Candidate supported acceptance is English
1/12, Hindi2/12 and Gujarati4/12. Twenty-nine supported examples are refused.
The selected cutoff is gate0.9/topic0.3/margin0.1. Zero observed false accepts
on this small synthetic set does not establish real-world safety. The result
rejects this candidate under its current data/training setup, not the possibility
of all hierarchical architectures.

A post-run **dev-only** grid summary (`dev-frontier.json`) shows the tradeoff:
within the frozen grid, zero false accepts permits at most8/18 supported accepts;
allowing one false accept permits16/18; allowing two permits18/18. These are
exploratory counts, not policy recommendations or validation. No thresholds were
relaxed and no new model was selected from this summary. In particular, the test
set was not searched for more flattering thresholds.

## Verification and limitations

Five focused tests passed. Independent source/scoring review confirmed train-only
centering, the topic-head positive-only mask, dev-only cutoff selection and all72
case IDs/labels/metrics. A second sequential process reproduces all deterministic
outputs exactly, excluding runtime/RSS. Reported loss samples occur before the
final optimizer update. The first run takes about8.01seconds and peaks at828400KiB
RSS using two CPU threads. No encoder finetuning, generative model, private corpus,
full application regression, runtime activation or physical robot test is involved.

```
python -m unittest -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
python probe.py --model-path /path/to/pinned/local/model
python dev_frontier.py
```

Retain sibling research directories for the original model manifests, training
inputs and seen-regression data. Downloaded encoder weights remain outside the
repository; newly fitted head weights exist only in process memory. No weights
are uploaded. No existing approval hold or private-source review is bypassed.

The failed split-gate approach makes another threshold-only iteration hard to
justify. A useful subsequent direction is substantially broader contrastive intent
training or a separately evaluated semantic reasoning model, with a genuinely new
untouched test and qualified language/domain review. Neither is completed here.
