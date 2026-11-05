# Actual CPU training, with a deliberately narrow claim

This experiment performs real, local gradient optimization and independent artifact reload at no external cost. It is a **fixed-catalogue evidence router**, not an LLM, a trained Jain reasoner, a general retriever, or an Agama knowledge model. It learns which of six original editorial notes is relevant to a query. Its result is a note ID, not an ethical decision or an answer. It is not connected to JACE runtime, safety decisions, memory, canonical admission, or the existing QLoRA trainer.

The existing QLoRA path still needs a rights-reviewed compatible local model, its ML dependencies, hardware qualification, real execution and useful quality validation. This separate experiment does not clear those gates. No Torch, Transformers, PEFT, GPU, remote model, paid API, or external training data was used here.

## Reproduce

From the repository root, with Python 3.10+ on Linux:

```sh
# Choose an existing writable parent. The output directory must not exist.
python scripts/train_evidence_router.py \
  --confirm-training --output /your/writable/parent/router-run

# Read-only: fresh interpreter, saved JSON parameters, all heldout scores.
python scripts/train_evidence_router.py \
  --reload /your/writable/parent/router-run/model.json

PYTHONPATH=src python -m unittest discover -s tests -p test_evidence_router.py -v
```

No installation or download is required. The CLI requires explicit training consent and a new output directory. It uses Linux limits of 30 CPU seconds, 256 MiB address space, 2 MiB per output file and 64 descriptors. The reload subprocess has a 30-second wall timeout. These are process/resource bounds, not a hostile-code sandbox. There is no separate wall timer on the initial training process. Direct low-level Python functions do not establish process limits and are for the bounded fixture/test workflow.

Outputs are a private directory with mode 0700 and inert JSON files with mode 0600. `model.json` contains only vocabulary, IDF values, learned numeric weights/biases, note IDs, rejection thresholds and fixture fingerprints. It uses no pickle, executable model code or third-party loader. `report.json` preserves every heldout query, expected label, rank, score, abstention and error. `COMPLETED.json`, written last, pins the model and report hashes. Handled failures produce `FAILED.json`; interrupted runs may leave incomplete files without a completion marker. Existing output is never overwritten. A completion marker proves this experiment's checks ran, not useful or safe deployment.

The recorded run is in [evals/evidence_router/2026-11-05](../evals/evidence_router/2026-11-05). Reports also pin the implementation files. The recorded model is an experiment artifact, never an automatically selected runtime model.

## Data and separation

All text is newly authored synthetic application material under this repository's MIT license. The six notes cover avoiding injury, resource needs, comparing accounts, qualifying conclusions, verifying textual attributions and checking permission. They are expressly noncanonical editorial notes, **not quotations or validated statements of Jain doctrine**. No collected text, translations, private memories, real user cases or public-domain source passages enter training.

The manifest pins the four input files by SHA-256 and declares source, license, synthetic kind, no personal data and no canonical/scholarly review. These declarations are not independent legal/privacy verification: falsely relabeling restricted material could deceive an attestation. That is not authorized. Duplicate normalized queries and IDs are rejected; family IDs must be disjoint; sizes, labels and vocabulary are bounded.

Before the first optimization, the corpus, examples, labels and optimizer were frozen:

| Split | Examples | Positives / negatives | Positive scenario families |
| --- | ---: | ---: | --- |
| Train | 48 | 48 / 0 | garden, balcony, cycling, picnic, workshop, pond, porch, orchard |
| Development | 16 | 12 / 4 | library, camp |
| Heldout | 32 | 24 / 8 | cleaning, wardrobe, dispute, hygiene |

Frozen file hashes:

- corpus.json: `e0a0c8dfad0615842ad8cb3bbf4ff163b8999dcec1f84aefe9f93c092657d0b7`
- train.json: `f40ac7dc1869e92ca2f98c8f37a35d3f33590bea291a4871eafb633ddc3d5a1f`
- development.json: `a91c9a8dda93edf3d1d8800484b72510eb8327f5f6d545c2b48011985f1b0ac6`
- heldout.json: `9f6412c7c2b7ae6204feebf59a9e05f0a8d6ac08b35057f04b7d26f8ca85f20f`

Important limitations:

- One author created all splits. Related concepts and phrasing recur. Family labels prevent only declared-family leakage, not semantic or paraphrase leakage. These are development fixtures, not an independently authored, sealed or representative benchmark.
- Positive scenario families differ, but every split routes to the **same six notes**. This tests new queries for a known catalogue, not new evidence documents, doctrinal transfer or open-ended retrieval.
- Negative family IDs are distinct, but their broad domains are not fully independent: both development and heldout contain arithmetic. The initial manifest overstated negative-domain separation; this descriptive metadata was corrected after the first run. No corpus/example/label bytes, hyperparameters, feature choices or threshold-selection rules were changed after viewing heldout results.
- The negative cases are few. No calibrated confidence, robust out-of-distribution rejection, multilingual competence, adversarial resilience or production coverage follows.

## Optimization and baselines

A linear multinomial classifier maps normalized TF-IDF query features to six note logits. Vocabulary and IDF use only training queries and the fixed catalogue. Heldout and development text do not build features or enter gradients. Full-batch gradient descent minimizes mean cross entropy plus L2 regularization. The fixed settings are 400 updates, learning rate 0.5, L2 coefficient 0.002 and zero initialization. No pretrained weights or randomly generated pretend training result is involved.

The heldout comparison includes raw token-intersection ranking (the existing store's basic approach, not its entire augmented runtime pipeline) and TF-IDF cosine ranking. All methods use deterministic ID tie-breaks. The stronger TF-IDF baseline uses the same train/catalogue-only vocabulary and IDF as the classifier.

Each method's rejection threshold is selected only on development decision accuracy from a predefined grid, preferring higher rejection on a tie. The grids and optimizer settings were not tuned on heldout results. Ranking metrics exclude no-relevant-note cases; rejection metrics include them. Softmax scores are not validated probabilities of correctness. The reported Wilson intervals are descriptive only; these authored examples are not random independent draws.

## Measured result: ranking improves, usable decisions do not

The actual run optimized 2,130 parameters. 1,860 weight coefficients changed from zero; the parameter displacement L2 norm was 13.9213. Regularized training loss decreased from **1.791759 to 0.602242**. The first and last recorded gradient L2 norms were 0.139221 and 0.026881. The final coefficient/bias hash is `380aa1641338de0212f8b04cae52b09310395044a1960b9aeb76bb3c2849015a`.

| Heldout measure | Raw lexical | TF-IDF | Trained router |
| --- | ---: | ---: | ---: |
| Correct first-ranked note, positives | 20/24 | 21/24 | 24/24 |
| Mean reciprocal rank | 0.8972 | 0.9306 | 1.0000 |
| Positive cases with an accepted note | 24/24 | 23/24 | 19/24 |
| Correct accepted results / all accepted | 20/27 | 21/24 | 19/20 |
| No-answer cases correctly rejected | 5/8 | 7/8 | 7/8 |
| Correct accepted note or correct rejection | 25/32 | **28/32** | **26/32** |

Thus the classifier improved this fixture's rank ordering, but **its rejection-aware result was worse than TF-IDF**. It is not justified to replace retrieval or activate the model based on this result. Heldout top-1 alone hides the cost of five abstentions and one false positive.

Preserved trained-model failures:

- It abstains on harm avoidance during a dispute, limits of zero-harm cleaning, necessary hygiene resource needs, uncertainty about keeping a jacket, and agreement to a business trial. These are relevant cases with scores below the development-selected 0.35 threshold.
- It incorrectly routes “What is the exact number resulting from this calculation?” to the provenance note, with score 0.3778. Surface cues such as “exact” do not establish textual relevance.

A fresh Python interpreter validates the saved model's numeric shape, bounds and catalogue/split hashes, then recomputes every heldout score, ranking and decision. All match exactly. Unit tests additionally check the analytic gradient against finite differences, repeat real optimization, verify feature isolation, reject malformed inputs and execute the full consent/training/reload CLI without a mocked backend. These establish that optimization and reload are real, not that the learned selection is reliable.

## Actual Jain reasoning readiness diagnostic

Run:

```sh
python scripts/evaluate_reasoning_readiness.py
PYTHONPATH=src python -m unittest discover -s tests -p test_reasoning_readiness.py -v
```

[Sixteen original application probes](../evals/reasoning/cases.json) are separate from all router data. The diagnostic runs the actual `CognitiveEngine` with `LocalReasoner`, a temporary synthetic-only database and the built-in unverified samples. It never calls a model provider. Full answers and generated perspective fields are preserved in [the observed report](../evals/reasoning/observed-2026-11-05.json).

Observed:

- 0/16 cases retrieve a reviewed canonical passage. Therefore **Jain doctrinal correctness is not scored**. An answer with an appropriate disclaimer does not demonstrate source knowledge.
- Only 3/9 cases requesting one of the existing practical plans match its template. Direct cleaning, wardrobe and business-partner wording works; three paraphrases, Hindi cleaning, Gujarati wardrobe and the negated-harm case do not.
- Tradition comparison, whether competing factual allegations are equally true, and a contextual seven-predicate explanation receive generic fallback text rather than the requested doctrinal analysis. Producing seven fields is not proof of valid sevenfold reasoning.
- An exact Agama verse request containing cleaning keywords triggers a generic cleaning plan plus the source limitation, not a verified verse answer.
- “I do not want to kill insects; how should I clean my room while avoiding injury?” is falsely rejected by the existing lexical harm policy. The explicit harmful request is also rejected. This is an observed defect, not a reason to weaken safety guards in this training experiment.
- Hindi/Gujarati prompts do not receive the requested practical plan or language-matched assistance. No multilingual reasoning is established.

These mechanical observations are **not a scholarly evaluation or a broad safety pass/fail score**. The probes were authored for readiness inspection, not sampled from real usage. The new router is deliberately disconnected, so this is not presented as a before/after improvement in generated answers.

## Remaining gates

For useful Agama-grounded reasoning: admit rights-cleared passages through the separate review workflow; obtain qualified review of edition, tradition, interpretation and labels; create an independently authored, versioned holdout with paraphrases, citation-support checks, conflicts, unanswerable questions and relevant languages; establish a baseline; choose and qualify a model/training environment; evaluate generated answers and their exact evidence; then decide whether any learned component should be deployed. Do not reuse these exposed heldout examples for a claim of unseen future performance. Rights clearance alone does not supply scholarly validation, and this CPU experiment does not supply either.
