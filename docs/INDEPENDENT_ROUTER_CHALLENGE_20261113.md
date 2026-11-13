# Independent synthetic router challenge, 2026-11-13

This is a **fixed six-note evidence-routing experiment**, not an LLM, Agama model,
Jain reasoning qualification, doctrinal validation or robot safety evaluation.
No runtime feature is activated and no model weights or source corpus are
published by this checkpoint.

## Execution and separation

The current executor has no Torch, Transformers or PEFT installation and no
`nvidia-smi` command. Rather than imply that an LLM was trained, this run used the
existing standard-library CPU router. It really performed 400 gradient updates
on the original training split, calibrated thresholds on the original development
split, and independently reloaded its numeric JSON artifact in a fresh process.
The 2,130-parameter run reproduced the original parameter hash
`380aa1641338de0212f8b04cae52b09310395044a1960b9aeb76bb3c2849015a`.
Training loss moved from 1.791759 to 0.602242. These are replication observations,
not a new training method or an improvement over the earlier model.

A separate review agent authored 18 new English queries after reading only the
six original synthetic editorial notes. It reported not reading training,
development, previous heldout queries, model parameters or prior results. Its
labels cover two positive queries per note and six unrelated queries, including
misleading word overlap. This separation reduces same-author leakage; it is not
an independently recruited human panel or a sealed external benchmark. Labels
remain editorial expectations, not religious authority.

The challenge was frozen before its first scoring run at SHA-256
`653ce92b05845d34505521f37b4276d4112a1d42a8271e6333934c833c8a4e8a`.
No weights, vocabulary, rejection thresholds or labels were changed after scoring.
The model and full local challenge/result files remain outside the publication.
This document is a results summary, not a self-contained reproduction bundle.

## Observed first-run results

| Measure | Lexical | TF-IDF | Trained router |
| --- | ---: | ---: | ---: |
| Correct top-ranked note among 12 positives | 5 | 5 | 10 |
| Correct accepted notes | 4 | 4 | 6 |
| All accepted notes | 13 | 9 | 6 |
| Unrelated queries correctly rejected, out of 6 | 2 | 5 | 6 |
| Correct accepted note or correct rejection, out of 18 | 6 | 9 | 12 |

The trained model improves this small challenge's routing decisions relative to
these baselines, but abstains on **six of twelve relevant requests**. Missing
positive coverage affects noninjury, consumption/restraint, perspectives,
conditional conclusions and consent. Accepting six correct answers out of six
accepted examples is not a reliability or safety guarantee. The earlier original
holdout still favored TF-IDF overall (28/32 versus trained 26/32); this new result
does not erase that failure. None of the methods generates or validates answers.

Decision: retain the model as an offline research component. Do not replace
runtime retrieval, announce broad Jain understanding, or publish a robot-safe
model. Further evaluation needs genuinely source-grounded answers and qualified
review, not just note selection or a larger count of synthetic examples.

## Reusable evaluation entry point

`python scripts/evaluate_router_challenge.py --model MODEL.json --challenge
CHALLENGE.json --challenge-sha256 SHA256` loads an existing locally saved router
bound to the original dataset. It validates the frozen bytes before evaluation,
rejects exact normalized query reuse across any original split, requires positive
and unrelated cases, retains every case, and compares all three methods with the
already saved development thresholds. It does not optimize or write files.
The stdout report contains query text; keep it private when inputs are private.
Hash and duplicate checks do not prove semantic independence or label accuracy.
Only use authorized material; this runner cannot grant rights or corpus admission.

## Verification

An independent review found no blocking issue in the runner and reproduced the
complete challenge report byte-for-byte with unchanged inputs. Eight targeted
checks pass, including an actual training/artifact-reload/evaluation subprocess
flow, repeated identical results, frozen-hash rejection, split-query overlap,
invalid labels and bounds. The existing eight-case application evaluation also
passes. These checks do not authenticate expert labels or expand model scope.
