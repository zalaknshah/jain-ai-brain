"""Prepare incomplete review bindings without model calls or source admission."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.model_output import strict_json
from jace.private_study import read_regular
from jace.source_answer_review import prepare_answer_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='Local saved evaluation input; command-line paths may be retained')
    parser.add_argument('--allow-local-disclosure', action='store_true', required=True,
                        help='allow case IDs and source/answer-derived hashes on stdout; not anonymized')
    args = parser.parse_args()
    try:
        raw = strict_json(read_regular(Path(args.input).absolute(), 8 * 1024 * 1024))
        if not isinstance(raw, dict) or set(raw) not in ({'cases', 'outputs'}, {'cases', 'outputs', 'reviews'}):
            raise ValueError('invalid evaluation input fields')
        report = prepare_answer_review(raw['cases'], raw['outputs'], raw.get('reviews'))
        serialized = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
        if len(serialized.encode('utf-8')) > 128 * 1024:
            raise ValueError('review draft output exceeds byte budget')
    except (ValueError, OSError, TypeError, RecursionError):
        parser.exit(2, 'Invalid or unavailable evaluation input; no review draft returned.\n')
    try:
        sys.stdout.write(serialized)
        sys.stdout.flush()
    except OSError:
        parser.exit(2, 'Unable to write review drafts; output may be incomplete.\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
