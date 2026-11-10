# Optional DeBERTa support comparison: pre-evaluation freeze

The subsequent [first paired results](PAIRED_SUPPORT_RESULTS.md) are now recorded
separately. This page preserves the pre-evaluation contract and its freeze checks.

This document describes preparation of an isolated candidate, **not comparison
results**. No claim of improved accuracy, reduced false support, generalization,
calibration, doctrinal competence, source truth or runtime suitability follows
from this implementation. Neither candidate is admitted to the JACE runtime.
There is no API/service integration, corpus access, automatic retrieval,
threshold tuning, quantization, fine-tuning, model publication or deployment here.

## Immutable candidate and separate version

- Runner: `scripts/predict_deberta_support.py`, version `deberta-support-v1`.
- Model: `cross-encoder/nli-deberta-v3-base`.
- Revision: `6c749ce3425cd33b46d187e45b92bbf96ee12ec7`.
- Standard implementation: `DebertaV2ForSequenceClassification`, despite the
  model's “v3” name. Twelve layers, hidden size 768, twelve attention heads,
  vocabulary size 128100, relative attention, FP32 and three model classes.
- The publisher's pinned README declares Apache-2.0. The manifest pins that
  card; it is not a legal audit of the model or training data.

The existing `scripts/predict_pretrained_support.py` remains untouched. Its
input validation and `run` function are reused without altering their behavior.
The new runner fails closed if either shared source hash changes:

| Shared file | SHA-256 |
| --- | --- |
| `scripts/predict_pretrained_support.py` | `11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e` |
| `scripts/evaluate_claim_support.py` | `f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13` |

Inspection output fingerprints the new runner, the frozen shared runner and
the unchanged schema independently. Its model/revision/backend identify
DeBERTa, never MiniLM. It also records all artifact hashes/sizes, Python,
PyTorch, Transformers, tokenizers, safetensors, huggingface-hub, NumPy, platform,
CPU/thread/determinism settings, loading diagnostics and checkpoint checks.
Source hashes identify bytes, not reviewer independence or semantic quality.

## Exact artifact manifest

The local model directory must contain exactly these seven regular files.
Every size and SHA-256 is checked before optional imports or model loading.
Symlink artifacts, symlink directories (including ancestors), extra files,
subdirectories and missing files are refused. Keep this trusted local directory
unchanged during a run; this is not a sandbox against a concurrent filesystem
writer replacing verified files during model loading.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `README.md` | 2,856 | `b6a6dd82d5fee7036e3b815ce1d28458df294d8525fc234fb7e7277b6b79d878` |
| `config.json` | 1,052 | `897e756eb59d3183adb505952e7910e7cbc7750a43f3b3747a96b688d2b02a47` |
| `tokenizer_config.json` | 1,346 | `f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6` |
| `special_tokens_map.json` | 301 | `ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712` |
| `added_tokens.json` | 26 | `a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23` |
| `tokenizer.json` | 8,656,624 | `5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964` |
| `model.safetensors` | 737,726,552 | `d8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa` |

Total: 746,388,757 bytes. `spm.model`, pickle weights, executable model code,
optimizer files and alternate checkpoints are not allowed. The runner does not
download, acquire dependencies, write result/cache/model files or fall back to
another model or tokenizer. Provisioning and synthetic preparation evidence
belong to a separate external experiment directory, not the runtime package.

## Fixed input and decision contract

The runner accepts only the existing gold-free export: protocol, dataset hash,
input hash and cases with exactly ID, passages, claim and citations. It checks
canonical input-hash binding, duplicate keys and IDs, finite JSON, bounded
regular-file input, exact citations, bounded text and forbidden control
characters. Gold labels, rationales, group IDs and extra fields are rejected.
Maximum batch size is 128 cases. The unchanged schema's input limit is 2 MiB.

For each case:

1. Join **all complete supplied passages**, in supplied order, with `\n\n`.
   Citations validate mechanical provenance only; they do not select or shorten
   the premise.
2. Tokenize premise first, claim second, with special tokens, no padding and
   `truncation=False`. Validate the resulting token arrays.
3. Count the actual complete pair, including special tokens. At 512 tokens a
   forward is allowed; above 512, emit `abstain` and
   `pair_token_limit_exceeded` **without a forward pass for that case**. Loading
   the backend occurs before case tokenization, so this is not a guarantee that
   an oversized input avoids model loading.
4. Run batch size one on CPU in eval/inference mode and require finite `[1, 3]`
   logits. Select raw argmax with deterministic first-index tie breaking:
   `0 -> contradicted`, `1 -> supported`, `2 -> not_established`.
   No thresholds, softmax-based decisions, candidate-label templates or
   quote-only inputs are used.

Tokenization errors, inference errors, malformed logits and nonfinite logits
produce explicit reason-coded abstentions, not replacement predictions.
Manifest, dependency, loading, configuration and malformed-input failures refuse
the entire invocation with status 2 and a stderr explanation. No successful
JSON is emitted on refusal. Successful stdout is exactly one bounded JSON
record. Optional-library stdout notices are redirected to stderr.

`predict` emits only the unchanged prediction schema; `inspect` adds identity,
policy, raw logits, per-case actual token lengths, reasons and premise hashes.
The inspected record should be retained with any externally scored predictions.

## Offline loading and trained-weight checks

Optional packages are imported lazily only after artifact verification. The
runner uses explicit standard DeBERTa classes, `local_files_only=True`,
`trust_remote_code=False`, `use_safetensors=True`, a serialized fast tokenizer,
and no slow-tokenizer conversion. Hub/Transformers offline and telemetry-off
flags are forced. No SentencePiece, protobuf, accelerate, sentence-transformers
or paid provider is required by this route. The prepared comparison reuses the
existing CPython 3.12/Linux x86-64 environment from
[`pretrained_support_requirements.lock`](../evals/pretrained_support_requirements.lock)
and its [official wheel manifest](../evals/pretrained_support_wheels.json),
without installing new packages. Those files are environment-specific provenance,
not a portable installer or a promise of identical results on other versions.

The tokenizer must be fast, case-sensitive, have vocabulary size 128000 and
length 128001, a 512-token advertised limit, no stored padding/truncation,
and the pinned special IDs (PAD 0, CLS/BOS 1, SEP/EOS 2, UNK 3, MASK 128000).
Its pair template must be `[CLS] A [SEP] B [SEP]`. Model architecture,
configuration and label order are checked explicitly.

Loading diagnostics are requested and recorded. Missing keys, mismatched
weights, loader errors or unknown unexpected keys cause refusal. The checkpoint
inventory is also checked **independently of Transformers' warning filters**:
every learned parameter must be present with its actual shape, CPU FP32 dtype
and exact loaded value equal to the safetensors tensor. The total is
184,424,451 learned elements. This detects missing or randomly initialized
learned weights even when framework diagnostics suppress a key.

The sole permitted nonlearned tensor is the old checkpoint's persisted
`deberta.embeddings.position_ids`: I64 shape `[1, 512]`, exactly `0..511`.
Modern Transformers reconstructs it as a nonpersistent buffer. Both stored and
runtime values are checked explicitly, even when loading diagnostics report no
unexpected keys. No new ignore-key patterns or blanket warning suppression are
installed. An unexpected learned position embedding is not allowed.

Execution fixes CPU FP32, one intra-op thread, one inter-op thread, Python and
PyTorch seed zero, deterministic Torch algorithms, eval mode and inference mode.
Thread-related environment variables are set to one before optional imports.
Use a fresh process; an already active process that cannot set inter-op threads
will refuse rather than silently use other settings. Determinism is not a claim
of exact numerical equivalence across platforms or dependency versions.

## Checks and operator commands

The normal synthetic boundary suite needs only Python's standard library:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests \
  -p test_deberta_support_boundary.py -v
```

It uses invented inert input strings, stub logits, fake tensor metadata and tiny
temporary artifact bytes. It checks manifest validation, loader flags, class and
label identity, missing/extra/randomly initialized learned weights, legacy
buffer checks, complete-pair ordering, boundaries, argmax/ties, abstentions,
strict input and bounded stdout. It reads no challenge, model-outcome fixture or
real model weights and needs no ML dependency installation. These are not
accuracy tests. Run broader tests separately under appropriate data separation;
the existing full suite includes disclosed challenge/outcome records.

For a separately authorized, already provisioned experiment, a fresh offline
process can be invoked as follows. Replace the explicit paths with the frozen
model directory and gold-free input export; there is no default challenge path.

```bash
PYTHONDONTWRITEBYTECODE=1 /path/to/isolated/venv/bin/python -B \
  scripts/predict_deberta_support.py inspect \
  --model-dir /path/to/pinned/model \
  --inputs /path/to/frozen/gold-free-inputs.json
```

The caller owns deadlines, wall-time/peak-RSS measurement and retention of the
first stdout/stderr and process status. The runner never writes those records.
The synthetic tests and separately performed loading/smoke checks do not
establish held-out performance. Before comparison inference, freeze/review this
runner, tests, source hashes, dependencies and artifact identity. Keep authors
and label reviewers blind to model identity and outcomes, preserve original
labels, and run both frozen candidates on the same newly sealed inputs. Retain
first outcomes and all failures without selecting favorable reruns. Evaluate
false support, coverage, supported recovery, full matched-group correctness,
phenomenon breakdowns and ambiguity sensitivity under rules fixed independently
of predictions. No release/admission decision is implied by this preparation.

## Observed freeze checks

Before any new comparison outcome was read, the candidate passed 25 implementation
boundary tests and 29 separate synthetic review tests. The full source suite ran
1,061 tests: 1,007 passed and 54 optional tests were skipped. These overlapping
checks are software tests, not 1,061 semantic-performance observations.

A separate real-backend validation loaded the pinned artifacts and independently
compared all 202 learned parameter tensors with the checkpoint. A newly invented
7,699-character premise produced 1,110 complete pair tokens, and the actual runner
returned the overflow abstention without calling backend logits or a model
forward. All forward calls were guarded against execution. This was a loading and
tokenizer check, not a new claim-support prediction.

The validation's unchanged network guard blocked an import-time IPv6 loopback
bind capability probe from urllib3. No outbound connection, DNS lookup or send
attempt was observed. Initial validation assertions incorrectly treated every
blocked socket event as an outbound attempt; their first logs were retained,
the counters and stack were inspected, and the final report separated the local
probe without weakening the guard or changing production code. Do not summarize
this as zero socket events or OS-enforced network isolation.

The actual comparison remains pending at this freeze checkpoint. A synthetic
preparation smoke and these boundary checks do not establish model accuracy.
