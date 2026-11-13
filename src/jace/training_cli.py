"""Offline explicitly reviewed QLoRA plan/run interface. No downloads."""
import argparse
import json

from .training import prepare_training, run_training


def main() -> None:
    parser = argparse.ArgumentParser(description='Plan or explicitly run bounded offline reviewed-data QLoRA')
    parser.add_argument('dataset', help='Local synthetic or separately reviewed Prakrit training JSONL')
    parser.add_argument('--evaluation', required=True, help='Separate held-out JSONL')
    parser.add_argument('--dataset-manifest', required=True, help='Schema-2 synthetic or schema-3 reviewed Prakrit provenance and revision-bound human review declarations')
    parser.add_argument('--model', required=True, help='Local built-in Llama safetensors directory, never a Hub ID')
    parser.add_argument('--model-manifest', required=True, help='Reviewed model provenance, rights and file hashes')
    parser.add_argument('--output', help='New private output directory; required to run')
    parser.add_argument('--steps', type=int, default=5)
    parser.add_argument('--sequence-length', type=int, default=128)
    parser.add_argument('--confirm-training', action='store_true', help='Explicitly run training on these inputs; default is non-executing preflight')
    args = parser.parse_args()
    common = (args.dataset, args.evaluation, args.dataset_manifest, args.model, args.model_manifest)
    try:
        if args.confirm_training:
            if not args.output:
                parser.error('--output is required with --confirm-training')
            result = run_training(*common, args.output, steps=args.steps, sequence_length=args.sequence_length, confirm_training=True)
        else:
            plan = prepare_training(*common, steps=args.steps, sequence_length=args.sequence_length)
            result = {'training_started': False, 'preflight_passed': True, 'train_records': len(plan['data']['train']),
                      'held_out_records': len(plan['data']['evaluation']), 'steps': plan['steps'],
                      'sequence_length': plan['sequence_length'], 'dataset_manifest_sha256': plan['data']['manifest_sha256'],
                      'model_manifest_sha256': plan['model']['manifest_sha256'],
                      'note': 'Admission checks only. Rights are operator attestations. Dependencies, GPU, model compatibility and training are unverified.'}
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
