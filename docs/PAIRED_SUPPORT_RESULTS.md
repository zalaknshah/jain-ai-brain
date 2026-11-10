# First frozen paired support trial

**Neither candidate is qualified for runtime semantic admission.** On this
newly authored fictional-English set, DeBERTa made more correct predictions and
fewer false-support predictions than MiniLM, but it still falsely supported
unsupported claims not flagged by reviewers and introduced errors the smaller model avoided.
The first trial and all disputed labels are preserved. No runtime, source rights,
corpus admission, main branch or deployment changed.

## Fixed comparison and original result

The DeBERTa adapter was [published before the trial](https://github.com/zalaknshah/jain-ai-brain/commit/03ae646fd8e30a7b3a50f6a38325e141296ecf17).
Both frozen candidates then ran once on the **same 120 new cases**: 40 matched
triples, five triples per phenomenon, and 40 original labels in each of the three
classes. Their first outputs were saved before scoring or reading gold. Both
used all supplied passages, fixed raw-logit argmax, no truncation and no threshold.
Neither candidate was tuned or rerun in response to this challenge's outcomes.

| Against original author labels | MiniLM | DeBERTa |
| --- | ---: | ---: |
| Correct / all cases | 73/120 (60.83%) | 84/120 (70%) |
| Unsupported called supported | 16/80 (20%) | 9/80 (11.25%) |
| Supported claims recovered | 22/40 (55%) | 22/40 (55%) |
| Complete triples correct | 7/40 | 17/40 |
| Predictions / abstentions | 120 / 0 | 120 / 0 |

These original-label scores include annotation disputes described below. They
are not a clean qualification benchmark. The identical MiniLM correct count in
its [earlier, different trial](PRETRAINED_SUPPORT_EXPERIMENT.md) is coincidental:
that trial had 11/80 false supports, whereas this paired trial has 16/80. Do not
compare DeBERTa's result to the earlier challenge as if the inputs were identical.

Gold-class confusion, in predicted order **supported / contradicted / not
established** (zero abstentions in every row):

| Gold class | MiniLM | DeBERTa |
| --- | --- | --- |
| Supported | 22 / 11 / 7 | 22 / 12 / 6 |
| Contradicted | 7 / 31 / 2 | 4 / 36 / 0 |
| Not established | 9 / 11 / 20 | 5 / 9 / 26 |

Correct cases by phenomenon, each initially containing 15 cases:

| Phenomenon | MiniLM | DeBERTa |
| --- | ---: | ---: |
| Negation | 14 | 13 |
| Quantity | 6 | 6 |
| Quantifiers | 9 | 13 |
| Time | 6 | 10 |
| Location | 10 | 12 |
| Conditionals | 8 | 8 |
| Attribution | 9 | 13 |
| Cross-source | 11 | 9 |

There is no uniform improvement across phenomena, and supported-claim recovery
did not improve. Matched triples share context; these are dependent observations,
not 120 independent trials from a real-world population. No confidence interval,
statistical-superiority claim or general-language reliability follows.

## Paired changes and concrete regressions

On the original 120 labels, 64 cases were correct under both candidates, 27 were
wrong under both, 20 changed from MiniLM-wrong to DeBERTa-correct, and 9 went the
other way. Of the 80 originally unsupported claims, 6 were falsely supported by
both, 10 only by MiniLM, and **3 only by DeBERTa**; 61 were falsely supported by
neither. Fewer errors in total does not mean every decision became safer.

Two newly introduced DeBERTa false supports remain outside every flagged group:

- `9cec964c26804fb3af471484a4856475`: a machine allows archive exit **only if**
  a packet has a wax seal. The packet has no seal and none is added. DeBERTa
  nevertheless supports the claim that it emerged at the archive end.
- `644ecee72a2244bab786f3ceef6319fb`: a seal is applied somewhere between 10:00
  and 10:20, with no relationship to a 10:12 break specified. DeBERTa supports
  the claim that the seal was applied before that break.

These examples are synthetic observations, not claims about every conditional
or temporal input. The third introduced false support concerns disputed source
attribution and is retained in the full result, then removed with its whole
matched group in the sensitivity analysis.

## Independent label review and unresolved scope

Two label-free reviews covered disjoint 60-case halves, one independent review
per case. The reviewers saw neither model identity nor outcomes, gold, author
notes or one another's review. Their primary labels agreed with the author in
**112/120** cases. There are **12 flagged cases across six groups**, including
all eight primary-label disagreements. The fixture text and original labels
have not been edited or silently corrected.

The disagreements are substantive annotation limitations: whether a reported
log or bulletin establishes a world fact, whether an animal falls under a
location-restricted rule, and whether a statement about one person's later
movement excludes earlier movement or another person's action. In particular,
reported claims must not automatically become verified facts. These ambiguities
need a clearer annotation contract; a higher model score cannot resolve them.

The challenge author used the task contract and evaluator schema and reports
inspecting no previous fixture, candidate implementation, model output or
benchmark report. **The output destination exposed a model-family name.** The
author reports not using that cue to tailor the cases or infer a checkpoint's
expected performance. Perfect model-identity blinding is not claimed. The
archived fixture's initial scope wording about independence from identities is
too broad; preserve its bytes as the historical input, but apply this explicit
qualification rather than repeating that wording as a verified fact.

### Whole-group sensitivity, not a replacement headline

The secondary view removes **every complete triple** containing any independent
ambiguity flag or primary disagreement, regardless of model outcome. This removes
18 cases in six groups, without changing any remaining label. It was computed
after inference from independently supplied flags, not selected to maximize a
candidate score.

| Remaining original labels | MiniLM | DeBERTa |
| --- | ---: | ---: |
| Correct / remaining cases | 61/102 (59.80%) | 71/102 (69.61%) |
| Unsupported called supported | 15/68 (22.06%) | 8/68 (11.76%) |
| Supported claims recovered | 19/34 | 18/34 |
| Complete triples correct | 6/34 | 14/34 |

This removes **four of five cross-source groups**, leaving just three cross-source
cases. Location and quantifiers each retain 12 cases; the other five phenomena
retain 15 each. The loss of cross-source coverage is material, not a minor footnote.
Label agreement on the remainder is not expert or external gold validation.
The subset still has two introduced DeBERTa false supports; it does not qualify a
gate or establish broad cross-source reasoning.

## Artifacts and reproduction

- `evals/paired_support_cases.json`: exact original 120-case fixture, including
  original gold, rationales and the qualified historical scope statement.
- `evals/paired_support_minilm_frozen.json` and
  `evals/paired_support_deberta_frozen.json`: byte-exact first inspection records,
  including predictions, raw logits, identities, reasons and token counts.
- `evals/paired_support_label_review.json`: all primary review labels, rationales
  and ambiguity flags, with exact input binding and assignment ranges.
- `evals/paired_support_observed.json`: artifact hashes, original confusion counts,
  paired changes, full-group exclusion, coverage loss, resources and limits.

The fixture SHA-256 is
`5efaa7095d8aa8403a2399ec4ce8818cde37f314beca833959b8ffe2d3995686`.
The shared canonical exported-input hash is
`2f5069bdbe645a789b9f18bf3816e363b753569bd4a3a15c462ff17db0ac3ccd`.
First inspection-record hashes are
`2db18a68e8aeb2e2d5a80747e3d49cdc9a0a5ceffad55f5fae2e9b4c763e9860`
for MiniLM and
`5fa17874f1ba72d511d1544cf3fb4dbe5827be473a8bfb50d136663a339436b6`
for DeBERTa. Local chronology and hashes bind retained content; they are not
independent execution attestation or proof of no related pretrained templates.

Recreate gold-free inputs with `evaluate_claim_support.py export`. Extract each
inspection record's `predictions` object and score it with the unchanged evaluator.
The ordinary replay tests use the standard library, not a new neural run.
Separate tokenizer-only checks reproduced all 240 recorded pair counts with
truncation and padding disabled; they are not extra performance samples.

## Runtime observations and boundaries

Both runs completed without abstentions, malformed model outputs or token clipping.
MiniLM pairs were 46–82 tokens, total 7,386; DeBERTa pairs were 43–78, total 7,067.
Different tokenizers make the totals noninterchangeable.

The single MiniLM process took 14.21 seconds and peaked at 631,708 KiB RSS; the
single DeBERTa process took 49.29 seconds and peaked at 1,898,624 KiB. Both used a
600-second timeout and 6-GiB address-space limit. These measurements include
artifact checks and loading, with different checkpoint sizes and weight-verification
work. One fixed run order, one process per model and unequal loading work do not
constitute a latency comparison or throughput benchmark.

Existing isolated, hash-pinned CPU dependencies were reused without new packages.
Each process had a clean separate HOME, cache and temporary directory, offline
flags and local-only safetensors loading. This was not an OS network namespace
or an inference-time network audit. Publisher license declarations and preparation
checks remain subject to their documented limits. Only original fictional text
was used; no private or religious corpus was sent to a model provider or admitted.

## Next useful work

Keep these outcomes as disclosed regression evidence. First clarify source-report
versus world-fact scope and other unresolved annotation rules, then verify that
contract with fresh independently reviewed cases. Candidate tuning, thresholds
or ensembles on this exposed set would require a new held-out evaluation. Merely
trying a larger model does not establish source truth, Jain scholarship, reliable
reasoning or a safe production gate.
