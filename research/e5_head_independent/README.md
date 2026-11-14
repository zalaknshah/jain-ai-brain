# Frozen multilingual E5 + trained softmax head experiment

**Result: rejected for runtime promotion.** This is an actual small CPU training
experiment, not a trained Jain reasoning model, scripture interpretation, robot
policy, scholarly translation, or product completion milestone.

## Experiment and temporal separation

The immutable official `intfloat/multilingual-e5-small` snapshot revision is
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. Its model card labels the model MIT.
Official file sizes/hashes are retained in `model-files.json`; weights are NOT in
this repository. Its low-resource language warning applies. Model licensing does
not supply rights to private corpus or books. No such content was used here.

The 36 training rows and 27 development rows are original assistant-authored
synthetic EN/HI/GU advisory prompts inherited from the earlier character-ngram
representation experiment. They are not scripture quotations, private material,
or human-reviewed translations. Six classes are editorial labels, not exhaustive
Jain doctrines or safety categories. Hashes are in `freeze.json`.

Protocol and runner hashes were frozen before heldout reading. Local checkpoint
`cf11893cabc106aaab0873fdc7b277da743d722b` saves protocol, training/development data,
runner, tests, model hashes and dev results. A separate assistant authored the
36-case holdout without reading train/dev/prior heldouts: 12 matched-language
scenario families, six supported and six unsupported, each in EN/HI/GU. Holdout
SHA256 is `ac14e5a28c0f3b56bc77bcf25e5497744b2aeb284fc59c8d2493d21985a0a278`.
This is independent assistant authoring, not blinded expert/human validation.
Exact ID/text and scenario-family cross-split checks passed; semantic independence
is not proved by these mechanical checks.

The encoder is frozen. A zero-initialized softmax linear head receives 400
full-batch gradient-descent updates (learning rate0.3, L2=.001). Cross entropy
falls from1.79176 to0.90133 before the final update. This genuinely trains the
classifier head, not the encoder. Weights exist only in process memory and are
not exported. Two CPU threads are used with8-row encoder batches and128-token
limit. Model loads use local files only, safetensors and remote-code disabled.
No external inference service is used.

The dev-only cutoff grid prioritizes zero false accepts, then useful coverage,
then higher cutoffs. Frozen dev-selected head cutoffs: probability0.3, margin0.1.
Prototype comparator: cosine0.9, margin0.05. These are distinct score scales.
The unchanged previous character-ngram runner was copied as `ngram_baseline.py`
and evaluated on this same fresh holdout with its original dev-only grid. It was
not optimized against these heldout outcomes.

## Observed results

| Method | Dev supported accepted correctly | Heldout supported accepted correctly | Heldout unsupported false accepts | Heldout abstentions |
|---|---:|---:|---:|---:|
| Trained E5 softmax head |14/18|0/18|0/18|36/36|
| Frozen E5 cosine prototypes |5/18|0/18|0/18|36/36|
| Previous English-only ngrams |See report|0/18|0/18|36/36|
| Previous multilingual ngrams |See report|0/18|0/18|36/36|

Every method has0/6 supported accepts in each of English, Hindi and Gujarati.
The18 correct unsupported abstentions must NOT be called50% reasoning competence
or a safe policy. A system that refuses everything has no useful coverage. The
independent prompts are longer/practical paraphrases; failure here demonstrates
that strong-looking dev results did not generalize. Do not tune on this now-seen
holdout and continue calling it unseen. Any revised experiment needs a separately
frozen protocol and another independently authored set.

## Resource and verification evidence

The first complete run took approximately5.03seconds and peaked at780676KiB RSS
on the current CPU container. This is a tiny frozen-encoder experiment, not an
estimate of full generative model training cost. Seven focused unit checks pass;
a separate process repeats all deterministic model/result fields exactly (see
`repeat-verification.json`), excluding elapsed time and RSS. No full JACE suite,
robot, deployment, private corpus or native Windows qualification was run.

Pinned top-level packages: torch2.7.1+cpu, transformers4.53.3, numpy2.2.6,
safetensors0.5.3. The complete installed dependency versions are recorded in
`requirements.observed.txt`. This is an observed package list, not a hash-locked
reproducible wheel archive. The model snapshot contains roughly493MB of files.

## Reproduce with reviewed official local model and dependencies

```
python -m unittest -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
python experiment.py --model-path /path/to/pinned/local/model --heldout
python ngram_baseline.py
```

Keep heavy runs sequential. Before reuse, verify `runner.freeze.sha256`, dataset
hashes and model file hashes. Scripts do not publish or promote results. This
new experiment does not retry or supersede any blocked public research upload.
Further progress needs better original synthetic train/dev diversity and expert
review objectives, not silent threshold lowering or unreviewed book ingestion.

A post-evaluation token-length diagnostic found no truncated rows: maximum token
lengths were26(train),26(dev),51(heldout), below the frozen128-token limit.
This excludes truncation as the cause of the observed zero-coverage result;
it does not establish why the learned head failed to generalize.
