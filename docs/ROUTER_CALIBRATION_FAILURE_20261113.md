# Fresh-development router calibration: failed candidate

This offline experiment tried to improve the **synthetic fixed-catalogue router**,
not a Jain language model. It did not use Agamas, transmit private texts, alter
trained weights, activate a runtime policy or produce robot control.

## Predeclared method and independent data

Two isolated authoring agents each read only the six synthetic editorial notes,
not training/dev/heldout files, learned parameters or previous results. One wrote
a 24-query development set, the other a separate 24-query holdout. Each contains
twelve positives (two per note) and twelve unrelated queries, including misleading
word overlap. Labels are authored editorial expectations, not expert judgments.
Exact normalized overlap with all original splits and between the new development
and holdout sets is rejected. Semantic overlap cannot be excluded by that check.

Before either new dataset was inspected, the candidate method was specified:
retain the existing learned weights and calibrate score plus top-two-score margin
on the new development set only. The frozen grid is score 0.15 through 0.95 in
0.05 steps plus 1.000001 (all-abstain fallback); margin 0 through 0.30 in 0.05 steps.
Among combinations with zero incorrect accepted selections on development, select
the highest correct acceptance count; break ties by higher score then higher
margin. Wrong-note positive selections and unrelated-query selections both count
as incorrect. This deliberately prioritizes precision, but is **not** a safety
proof or calibrated probability of correctness.

Frozen inputs and selection:

- Development SHA-256: `db8b33b7952c6076c4819918685ac67d123e9ce5483a09acef53c3c85b94fc9b`
- Holdout SHA-256: `eee2a25e7a2c1f92d557803ffdfd1a0908b9c0f7eff3b328e5d3e4e5328cbd3a`
- Frozen selection SHA-256: `04b3344f90b7ae090acbc4bfa83b2f01f9cbb373fdc7717d8867a151b5ac6210`
- Runner SHA-256 at first scoring: `2762a227a54fd4b1b83da7cd7b78456a242381f38ae1d0a48c16033e23bfebdf`

The selected rule was **score at least 0.40 and margin at least 0.20**. It accepted
5/12 relevant development queries, rejected all twelve unrelated development
queries, and made no incorrect accepted selection there. The artifact was saved
and hashed before the holdout was first read/scored. No subsequent tuning occurred.

## First untouched-holdout result

| Measure | Original trained threshold | New score+margin rule |
| --- | ---: | ---: |
| Correct accepted relevant queries / 12 | 5 | 3 |
| Relevant queries abstained / 12 | 7 | 9 |
| Unrelated queries rejected / 12 | 11 | 11 |
| Incorrect accepted selections | 1 | 1 |
| Correct decisions / 24 | 16 | 14 |

The candidate **regressed**. It discarded two previously correct relevant
selections without removing the false selection. Zero development errors did not
transfer even to this tiny, freshly authored holdout. TF-IDF scored 12/24 and raw
lexical selection 7/24 on the same set; the original trained router ranked the
correct note first for 9/12 positives. Routing success is not answer support or
Jain doctrinal correctness.

Decision: reject this calibration candidate for promotion. Keep original routing
research offline too. Do not retune against these now-exposed holdout examples
and call the result unseen performance. The next useful improvement needs better
representations/training evidence and genuinely fresh evaluation, not looser
claims, more calibration parameters or suppressing abstentions.

## Reusable offline runner

`calibrate_router_selection.py --calibrate` reads an explicitly hashed development
challenge and prints an inert selection JSON object. Redirect stdout to a new
private file if retaining it. `--selection FILE` instead reads that frozen rule,
checks its full numeric-model binding and rejects development/holdout exact query
overlap, then reports both the candidate and original methods on a hashed holdout.
The CLI never retrains, changes thresholds during evaluation or writes files.
The artifact and hashes detect mismatches; they are not signatures, expert
credentials or evidence that someone could not manufacture a different rule.
Challenge/raw result/model artifacts remain local; this source checkpoint is not
a self-contained public reproduction dataset.

## Local checks

The runner's nine focused selection checks passed. The full local suite ran
850 tests: 796 passed and 54 optional tests skipped. The existing eight-case
application evaluation passed. Repeating the frozen holdout invocation produced
byte-identical output. No test outcome turns this failed candidate into a
qualified routing or safety policy.
