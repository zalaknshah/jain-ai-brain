"""Private capped QLoRA worker; no imports of optional ML packages before limits."""
from __future__ import annotations

import json
from contextlib import redirect_stdout
import math
import os
import resource
import shutil
import sys
from pathlib import Path

from .training import ADDRESS_BYTES, CPU_SECONDS, WALL_SECONDS, MAX_DATA_BYTES, MAX_MODEL_BYTES, FILES, _json, _read, _sha, prepare_training


def _limits() -> dict:
    for kind, value in [(resource.RLIMIT_AS, ADDRESS_BYTES), (resource.RLIMIT_CPU, CPU_SECONDS),
                        (resource.RLIMIT_FSIZE, 64 * 1024**2), (resource.RLIMIT_NOFILE, 128)]:
        resource.setrlimit(kind, (value, value))
    return {'address_space_bytes': resource.getrlimit(resource.RLIMIT_AS)[0],
            'cpu_seconds': resource.getrlimit(resource.RLIMIT_CPU)[0], 'outer_wall_seconds': WALL_SECONDS,
            'file_bytes': resource.getrlimit(resource.RLIMIT_FSIZE)[0]}


def _train_qlora(plan: dict, model_path: Path, stage: Path) -> dict:
    try:
        import torch
        import transformers
        import peft
        from transformers import BitsAndBytesConfig, LlamaConfig, LlamaForCausalLM, PreTrainedTokenizerFast
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        import bitsandbytes
        import safetensors
    except ImportError as error:
        raise RuntimeError('Optional training dependencies are unavailable. No installation or download is performed.') from error
    if not torch.cuda.is_available():
        raise RuntimeError('This QLoRA implementation requires a compatible local CUDA GPU; CPU and mock results are not substituted.')
    torch.set_num_threads(1)
    torch.manual_seed(0)
    # This limits the PyTorch allocator, not all CUDA memory or other processes.
    torch.cuda.set_per_process_memory_fraction(0.25, device=0)
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(model_path / 'tokenizer.json'))
    config = LlamaConfig(**plan['model']['config'])
    if any(type(token) is not int or not 0 <= token < config.vocab_size for token in tokenizer.get_vocab().values()):
        raise ValueError('tokenizer IDs exceed model vocabulary')
    if type(config.eos_token_id) is not int or not 0 <= config.eos_token_id < config.vocab_size:
        raise ValueError('one valid EOS token ID is required')
    # Encode every example before allocating the model; never silently truncate answers.
    def encode(row):
        prompt = tokenizer.encode('Instruction:\n' + row['instruction'] + '\nResponse:\n', add_special_tokens=False)
        answer = tokenizer.encode(row['response'], add_special_tokens=False)
        if not prompt or not answer:
            raise ValueError('each example must contain prompt and response tokens')
        ids = prompt + answer + [config.eos_token_id]
        if len(ids) > plan['sequence_length']:
            raise ValueError('example exceeds token budget; no automatic truncation')
        return ids, [-100] * len(prompt) + answer + [config.eos_token_id]
    train = [encode(row) for row in plan['data']['train']]
    evaluation = [encode(row) for row in plan['data']['evaluation']]
    model, loading = LlamaForCausalLM.from_pretrained(
        str(model_path), config=config, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, output_loading_info=True, device_map={'': 0}, torch_dtype=torch.float16,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                                              bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16))
    if any(loading.get(key) for key in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
        raise RuntimeError('base model tensors do not exactly match the built-in architecture; no random missing weights are accepted')
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=4, lora_alpha=8, lora_dropout=0.0, bias='none',
                                           target_modules=['q_proj', 'v_proj'], task_type='CAUSAL_LM'))
    trainable = [(name, parameter) for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable or any('lora_' not in name for name, _ in trainable):
        raise RuntimeError('only LoRA adapter parameters may be trained')
    count = sum(parameter.numel() for _, parameter in trainable)
    if count > 131072:
        raise RuntimeError('trainable adapter exceeds parameter budget')
    optimizer = torch.optim.AdamW([p for _, p in trainable], lr=0.0002)
    def loss_for(example):
        ids, labels = example
        return model(input_ids=torch.tensor([ids], device='cuda:0'),
                     attention_mask=torch.ones((1, len(ids)), dtype=torch.long, device='cuda:0'),
                     labels=torch.tensor([labels], device='cuda:0')).loss
    def evaluate():
        model.eval()
        summed, count = 0.0, 0
        with torch.no_grad():
            for example in evaluation:
                token_count = sum(label != -100 for label in example[1][1:])
                loss = float(loss_for(example).item())
                if not math.isfinite(loss):
                    raise RuntimeError('nonfinite evaluation loss')
                summed += loss * token_count; count += token_count
        return summed / count
    before = evaluate()
    initial = [parameter.detach().cpu().clone() for _, parameter in trainable]
    model.train()
    losses = []
    for step in range(plan['steps']):
        optimizer.zero_grad(set_to_none=True)
        loss = loss_for(train[step % len(train)])
        value = float(loss.item())
        if not math.isfinite(value):
            raise RuntimeError('nonfinite training loss')
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_([p for _, p in trainable], 1.0, error_if_nonfinite=True)
        if not math.isfinite(float(norm.item())):
            raise RuntimeError('nonfinite gradient norm')
        optimizer.step(); losses.append(value)
    after = evaluate()
    changed = any(not torch.equal(old, parameter.detach().cpu()) for old, (_, parameter) in zip(initial, trainable))
    if not changed:
        raise RuntimeError('adapter parameters did not change; training is not complete')
    model.save_pretrained(str(stage), safe_serialization=True, save_embedding_layers=False)
    return {'backend': 'cuda-bitsandbytes-nf4-peft-lora', 'training_steps': len(losses),
            'trainable_parameters': count, 'adapter_parameters_changed': changed,
            'training_loss_first': losses[0], 'training_loss_last': losses[-1],
            'held_out_response_token_loss_before': before, 'held_out_response_token_loss_after': after,
            'quality_improvement_claimed': False, 'gpu_allocator_fraction': 0.25,
            'versions': {'torch': torch.__version__, 'transformers': transformers.__version__, 'peft': peft.__version__, 'bitsandbytes': bitsandbytes.__version__, 'safetensors': safetensors.__version__}}


def _verify_export(stage: Path) -> dict:
    # PEFT generates a model card by default; it is not part of this bounded export.
    card = stage / 'README.md'
    if card.exists():
        if card.is_symlink() or not card.is_file():
            raise ValueError('unexpected model-card artifact')
        card.unlink()
    if {p.name for p in stage.iterdir()} != {'adapter_model.safetensors', 'adapter_config.json'}:
        raise ValueError('unexpected adapter export files')
    raw = _read(stage / 'adapter_model.safetensors', 8 * 1024**2)
    if len(raw) < 8:
        raise ValueError('invalid adapter safetensors')
    length = int.from_bytes(raw[:8], 'little')
    if not 2 <= length <= 65536 or length + 8 > len(raw):
        raise ValueError('invalid adapter header')
    header = _json(raw[8:8 + length])
    if not isinstance(header, dict):
        raise ValueError('invalid adapter tensor inventory')
    tensor_names = [name for name in header if name != '__metadata__']
    if not tensor_names or len(tensor_names) > 64 or any(not (name.endswith('.lora_A.weight') or name.endswith('.lora_B.weight')) for name in tensor_names):
        raise ValueError('export contains non-adapter weights')
    # Validate the format with the official safe parser, not pickle.
    from safetensors import safe_open
    with safe_open(str(stage / 'adapter_model.safetensors'), framework='pt', device='cpu') as handle:
        if sorted(handle.keys()) != sorted(tensor_names):
            raise ValueError('adapter inventory mismatch')
        if sum(math.prod(handle.get_slice(name).get_shape()) for name in tensor_names) > 131072:
            raise ValueError('export exceeds adapter parameter budget')
    config_path = stage / 'adapter_config.json'
    config = _json(_read(config_path, 65536))
    if not isinstance(config, dict) or config.get('peft_type') != 'LORA' or config.get('task_type') != 'CAUSAL_LM' or config.get('auto_mapping') not in (None, {}):
        raise ValueError('unexpected adapter configuration')
    config['base_model_name_or_path'] = ''  # Base identity is recorded by content hashes, never a local private path.
    config['revision'] = None
    config_path.write_text(json.dumps(config, indent=2, allow_nan=False) + '\n')
    return {p.name: _sha(_read(p, 8 * 1024**2)) for p in stage.iterdir()}


def execute(job: dict) -> dict:
    expected_keys = {'train', 'evaluation', 'dataset_manifest', 'model', 'model_manifest', 'output', 'steps', 'sequence_length', 'expected_dataset', 'expected_model', 'confirm_training'}
    if not isinstance(job, dict) or set(job) != expected_keys:
        raise ValueError('invalid worker job schema')
    if job.get('confirm_training') is not True:
        raise ValueError('worker requires explicit training confirmation')
    limits = _limits()
    plan = prepare_training(job['train'], job['evaluation'], job['dataset_manifest'], job['model'], job['model_manifest'],
                            steps=job['steps'], sequence_length=job['sequence_length'])
    if plan['data']['manifest_sha256'] != job['expected_dataset'] or plan['model']['manifest_sha256'] != job['expected_model']:
        raise ValueError('reviewed inputs changed after preflight')
    output = Path(job['output'])
    if not output.is_absolute() or output.parent.absolute() != output.parent.resolve():
        raise ValueError('output must have a non-symlink absolute parent')
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    stage = output / '.working'; stage.mkdir(mode=0o700)
    os.environ.update({'HOME': str(output), 'HF_HOME': str(output / '.cache'), 'HF_HUB_OFFLINE': '1',
                       'HF_DATASETS_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                       'DO_NOT_TRACK': '1', 'WANDB_MODE': 'disabled'})
    inputs = output / '.inputs'
    inputs.mkdir(mode=0o700)
    try:
        # Train against private snapshots, never mutable original source paths.
        staged = {}
        for key in ('train', 'evaluation', 'dataset_manifest', 'model_manifest'):
            staged[key] = inputs / (key + '.json')
            staged[key].write_bytes(_read(Path(job[key]), MAX_DATA_BYTES if key in ('train', 'evaluation') else 16384))
        local_model = inputs / 'model'; local_model.mkdir(mode=0o700)
        for name in FILES:
            (local_model / name).write_bytes(_read(Path(job['model']) / name, MAX_MODEL_BYTES if name.endswith('.safetensors') else MAX_DATA_BYTES))
        frozen = prepare_training(staged['train'], staged['evaluation'], staged['dataset_manifest'], local_model, staged['model_manifest'],
                                  steps=job['steps'], sequence_length=job['sequence_length'])
        if frozen != plan:
            raise ValueError('inputs changed while making the private snapshot')
        with redirect_stdout(sys.stderr):
            metrics = _train_qlora(frozen, local_model, stage)
        # Recheck file declarations after execution, before marking a run complete.
        after = prepare_training(job['train'], job['evaluation'], job['dataset_manifest'], job['model'], job['model_manifest'],
                                 steps=job['steps'], sequence_length=job['sequence_length'])
        if after != plan:
            raise ValueError('inputs changed during execution; no completed adapter is published')
        artifacts = _verify_export(stage)
        shutil.rmtree(inputs)
        if (output / ".cache").exists():
            shutil.rmtree(output / ".cache")
        report = {'completed': True, 'metrics': metrics, 'resource_limits': limits,
                  'train_records': len(plan['data']['train']), 'held_out_records': len(plan['data']['evaluation']),
                  'dataset_manifest_sha256': plan['data']['manifest_sha256'], 'model_manifest_sha256': plan['model']['manifest_sha256'],
                  'base_files': plan['model']['files'], 'adapter_files': artifacts,
                  'scope': 'Synthetic-only bounded adapter experiment; no Jain reasoning, safety or corpus qualification',
                  'remote_published': False}
        encoded = json.dumps(report, indent=2, allow_nan=False) + '\n'
        # Root is an exclusively created private directory. Incomplete runs lack manifest.json.
        stage.rename(output / 'adapter')
        (output / '.manifest.tmp').write_text(encoded)
        (output / '.manifest.tmp').replace(output / 'manifest.json')
        return report
    except Exception:
        if inputs.exists():
            shutil.rmtree(inputs)
        (output / 'FAILED.json').write_text('{"completed": false, "note": "Incomplete local run; do not use staged artifacts."}\n')
        raise


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('worker job exceeds size limit')
        report = execute(_json(raw))
        print(json.dumps(report, allow_nan=False))
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()
