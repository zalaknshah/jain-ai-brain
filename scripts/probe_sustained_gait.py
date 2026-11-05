"""Run the isolated six-step finite-horizon experiment, never a hardware command."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.freebase_sustained import MAX_STEPS, SCENARIOS, run_sustained_probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-simulation', action='store_true')
    parser.add_argument('--scenario', choices=SCENARIOS, default='neutral_posture')
    parser.add_argument('--steps', type=int, default=MAX_STEPS)
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args()
    try:
        report = run_sustained_probe(args.scenario, steps=args.steps,
                                     confirm_simulation=args.confirm_simulation, include_trace=args.trace)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
