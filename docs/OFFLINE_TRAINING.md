# Bounded offline training path

The former `train_qlora.py` script only printed suggested steps. It is now an explicit preflight/run interface with dataset admission, an offline NF4/LoRA training implementation, held-out loss measurement and guarded adapter export. **Actual model training has not been validated.** The development machine has no CUDA GPU or installed Torch/Transformers/PEFT/bitsandbytes stack. Tests validate admission and orchestration with synthetic fixtures and mocks; a real capped subprocess verifies only the early missing-dependency failure path.

No model weights were downloaded, dependencies installed, private conversations used, or collected Jain texts admitted. This slice accepts only datasets explicitly declared synthetic. A compatible, rights-reviewed local base checkpoint and a separately provisioned, tested GPU environment are still needed before a real run can qualify this implementation.

## Default: inspect without training

```sh
python scripts/train_qlora.py training/fixtures/train.jsonl \
  --evaluation training/fixtures/evaluation.jsonl \
  --dataset-manifest training/fixtures/manifest.json \
  --model /absolute/path/to/local-small-llama \
  --model-manifest /absolute/path/to/model-manifest.json
```

The installed wheel provides the equivalent `jace-train` command (or `python -m jace.training_cli`). The fixture files are checkout examples, not automatically loaded by the installed package.

The default validates bounded local files and prints a plan. It does not import optional ML dependencies, allocate a model, create an output directory, install packages, download files or start training. Passing preflight does not prove that model tensors match the architecture, that tokenization fits, or that training will run.

Training additionally requires both `--confirm-training` and `--output /absolute/path/to/new-private-run`. It is never called from the conversational runtime, memory store, browser learning flow or corpus collector. There is no background training and no implicit confirmation. Existing output directories are rejected. No model, checkpoint, metrics or dataset is automatically uploaded or pushed.

## Dataset and rights gates

Each JSONL record has exactly `id`, `instruction` and `response`. Both train and held-out files are required. Each split permits at most 256 nonempty records, at most 4096 characters per text field and at most 2 MiB total. The supplied original synthetic fixtures contain three training examples and two evaluation examples about arbitrary color labels. They are not a Jain instruction dataset or an ethical reasoning benchmark.

The separate dataset manifest requires:

- `schema_version: 1` and `data_kind: "synthetic"`;
- nonempty `source` and `license`;
- `rights_reviewed: true`, `content_reviewed: true`, `contains_personal_data: false`;
- exact `train_sha256` and `evaluation_sha256` values.

These are operator attestations tied to exact bytes, not independent legal, scholarly or privacy verification. The software cannot prove that falsely labeled data is synthetic. Memory exports and collected source corpora must not be relabeled to bypass this boundary. Admission of non-synthetic material remains a separate future gate requiring actual rights and content review.

Duplicate IDs and Unicode-normalized, case-folded, whitespace-normalized duplicate prompts are rejected across and within the splits. This catches exact normalized leakage, not paraphrases or semantic overlap. Held-out prompts never enter the optimization loop. Any response-token loss is diagnostic only; no improvement in quality, factuality or safety is inferred.

## Local model restrictions

Only a flat, non-symlink local directory containing exactly these files is accepted:

- `config.json`, for the built-in `LlamaForCausalLM` architecture;
- self-contained `tokenizer.json`, with a built-in WordLevel or BPE model;
- one unsharded `model.safetensors`, containing ordinary floating-point base weights.

The model-rights manifest contains `source`, `license`, `rights_reviewed: true` and a `files` object mapping those exact filenames to SHA-256 hashes. Attestation is not independent rights clearance. Extra files, Python, pickle/bin/pt formats, shard indexes, custom configuration mappings and symlinked paths are rejected. Header byte ranges, dimensions, parameter counts and configuration allocation estimates are checked before model allocation. The base file is limited to 64 MiB and the conservative configuration/tensor budgets to 16 million parameters. This intentionally excludes most real-world LLM checkpoints.

Execution makes private input snapshots and verifies them against preflight before loading. It calls explicit built-in classes, uses `local_files_only=True`, `trust_remote_code=False` and `use_safetensors=True`, and rejects missing, unexpected or mismatched base tensor load results. It does not fall back to random missing weights. Tokenization happens before model allocation; every example must fit, with no silent response truncation.

## Execution and export bounds

The Linux worker has a 4 GiB address-space limit, 120 CPU seconds, an outer 180-second wall limit, a 64 MiB per-file limit and 128 open descriptors. Limits are established before optional ML imports. CPU/thread settings are bounded to one. The implemented CUDA path limits the PyTorch allocator to 25% of device memory, which is **not** an OS GPU quota or a limit on other CUDA processes. Some otherwise valid GPU environments may fail the conservative address-space cap. Failure does not trigger an automatic retry or a larger limit.

The child receives a minimal environment without inherited credential variables, disables user-site imports, uses the trusted package directory, and enables Hugging Face offline/telemetry-disable flags. No Hub ID, remote adapter, tracking integration or arbitrary code loader is used. These are application controls, not a security sandbox against malicious installed libraries or another process with the same account privileges.

The implementation uses 4-bit NF4 base loading, rank-4 LoRA on query/value projections, frozen base weights, batch size one, a fixed seed, AdamW, gradient clipping, at most 20 updates and a sequence cap of 256. Prompt labels are masked; response and EOS tokens contribute to training. Nonfinite losses/gradients or unchanged adapter parameters abort the run. Before/after held-out response-token loss and dependency versions are recorded, without requiring or claiming improvement.

Exports are limited to adapter safetensors and an adapter configuration. Base weights and tokenizer files are not exported. Local base paths are removed from adapter metadata; base identity is recorded by hashes. A new private output directory contains staged work, then a validated `adapter` directory. The completed `manifest.json` is published last via atomic replacement and is the success marker. A normal failure leaves no completed manifest and records `FAILED.json`; interrupted/killed runs may leave private incomplete staging files. Never treat those as completed adapters. Private input copies are removed on normal success or handled exceptions. No existing user output is overwritten.

## Evidence and remaining gate

Run the dependency-free tests with:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_training.py -v
```

Successful worker/export flow tests explicitly mock training and export verification. The inert safetensors header fixture in tests is not a compatible base model and is never passed to a real ML loader. No real gradients, GPU quantization, optimizer compatibility, learned answers, convergence, adapter reload or model-quality evaluation have been demonstrated. A genuine run plus independent artifact reload and held-out behavior evaluation remain required. Until then, this is a guarded implementation awaiting backend qualification, not a working trained JACE model.

Implementation references: [PEFT quantization guide](https://huggingface.co/docs/peft/developer_guides/quantization), [Transformers offline loading](https://huggingface.co/docs/transformers/main/installation#offline-mode), and [Transformers artifact security guidance](https://github.com/huggingface/transformers/blob/main/SECURITY.md). The installed dependency versions must be selected and qualified together in the eventual training environment; none is silently installed by this tool.

### Exact tokenized split collisions

The worker checks the actual encoded prompt sequences before loading the model.
Different text can become the same model input through tokenizer normalization or
unknown tokens. Such a collision, within either split or between training and
held-out evaluation, now rejects the experiment even if the answers differ.
Encoded prompt and response token IDs must also lie within the model vocabulary.
Answer tokens and EOS still contribute to loss; prompt tokens remain masked, and
examples exceeding the sequence budget are rejected rather than truncated.

These are exact token-input checks, not a semantic independence test. Paraphrases,
related source passages, reused answer templates and broader dataset contamination
still require separate evaluation design. No new model was trained or qualified by
this change. Validation uses a synthetic tokenizer and no optional ML packages.
