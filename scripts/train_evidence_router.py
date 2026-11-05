"""Run or independently reload the bounded original synthetic CPU experiment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.evidence_router import (LIMITS, calibrate, digest, encoded, evaluate, fit, load_dataset, load_model)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT/'training/evidence_router')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--confirm-training', action='store_true')
    parser.add_argument('--reload', type=Path, help='read inert JSON model and score heldout; no optimization')
    args = parser.parse_args()
    if args.reload is not None and (args.confirm_training or args.output is not None):
        parser.error('--reload is read-only and cannot be combined with training/output')
    if args.reload is None and (not args.confirm_training or args.output is None):
        parser.error('new --output directory and --confirm-training required; no training started')
    if sys.platform != 'linux':
        parser.error('bounded command currently requires Linux resource limits')
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2*1024**2, 2*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    data = load_dataset(args.dataset)
    if args.reload is not None:
        model = load_model(args.reload, data)
        print(encoded({method: evaluate(model, data['corpus'], data['heldout'], method, model['thresholds'][method])
                       for method in ('lexical', 'tfidf', 'trained')}).decode(), end='')
        return 0
    output = args.output.absolute()
    if output.exists() or output.is_symlink() or output.parent != output.parent.resolve() or not output.parent.is_dir():
        raise ValueError('output must be new under an existing non-symlink parent; nothing is overwritten')
    output.mkdir(mode=0o700)
    def write(name, value):
        # New private directory; exclusive writes, no pickle or executable exports.
        with (output/name).open('xb') as handle:
            os.chmod(handle.fileno(), 0o600)
            handle.write(encoded(value))
    started = time.monotonic()
    try:
        model, proof = fit(data['train'], data['corpus'])
        model.update(manifest_sha256=data['manifest_sha256'], corpus_sha256=data['manifest']['files']['corpus.json'],
                     thresholds={method: calibrate(model, data['corpus'], data['development'], method) for method in ('lexical','tfidf','trained')})
        before_reload = {method: evaluate(model, data['corpus'], data['heldout'], method, model['thresholds'][method]) for method in ('lexical','tfidf','trained')}
        write('model.json', model)
        # A new interpreter parses and validates the saved parameters, then
        # recomputes every heldout score/rank/decision. No trainer state is passed.
        child = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--dataset', str(args.dataset.absolute()), '--reload', str(output/'model.json')],
                               capture_output=True, timeout=30, check=True,
                               env={'PATH': os.environ.get('PATH',''), 'PYTHONNOUSERSITE':'1', 'PYTHONDONTWRITEBYTECODE':'1'})
        reloaded = json.loads(child.stdout)
        if reloaded != before_reload:
            raise ValueError('fresh-process reload scores differ')
        report = {'scope': LIMITS, 'manifest_sha256': data['manifest_sha256'], 'fixture_files': data['manifest']['files'],
                  'split_policy': data['manifest']['split_policy'],
                  'implementation_sha256': {name:digest((ROOT/name).read_bytes()) for name in ('src/jace/evidence_router.py','scripts/train_evidence_router.py')},
                  'splits': {s: {'cases':len(data[s]), 'positive':sum(bool(x['relevant']) for x in data[s]),
                                'families':sorted({x['family'] for x in data[s]})} for s in ('train','development','heldout')},
                  'optimization': proof, 'heldout': before_reload,
                  'reload': {'fresh_python_process':True, 'exact_all_case_scores_rankings_and_decisions':True,
                             'model_sha256':digest((output/'model.json').read_bytes())},
                  'environment': {'python':sys.version.split()[0], 'backend':'Python standard library, CPU', 'external_dependencies':[],
                                  'limits':{'cpu_seconds':30,'address_bytes':256*1024**2,'file_bytes':2*1024**2},
                                  'elapsed_seconds':time.monotonic()-started}}
        write('report.json', report)
        # Written last; failed runs have no completion marker.
        write('COMPLETED.json', {'model_sha256':report['reload']['model_sha256'], 'report_sha256':digest((output/'report.json').read_bytes()), 'scope':LIMITS})
        print(json.dumps({'output':str(output), 'optimization':proof, 'heldout': {key:{k:v for k,v in value.items() if k!='cases'} for key,value in before_reload.items()},'reload':report['reload'],'scope':LIMITS}, indent=2))
    except Exception as error:
        write('FAILED.json', {'error':type(error).__name__, 'message':str(error)[:1000]})
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
