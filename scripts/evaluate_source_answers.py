"""Inspect saved local answers, without executing a model or admitting a corpus."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.model_output import strict_json
from jace.private_study import read_regular
from jace.source_answer_eval import evaluate_source_answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Local JSON object with cases, outputs and optional reviews')
    args = parser.parse_args()
    try:
        raw = strict_json(read_regular(Path(args.input).absolute(), 8 * 1024 * 1024))
        if not isinstance(raw, dict) or set(raw) not in ({'cases', 'outputs'}, {'cases', 'outputs', 'reviews'}):
            raise ValueError('input requires only cases, outputs and optional reviews')
        report = evaluate_source_answers(raw['cases'], raw['outputs'], raw.get('reviews'))
    except (ValueError, OSError, TypeError, RecursionError):
        parser.exit(2, 'Invalid evaluation input; no model or source admission performed.\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    # Successful inspection is not a quality pass; inspect the separate fields.
    return 0


if __name__ == '__main__': raise SystemExit(main())
