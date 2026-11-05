"""Separate resource-capped process for the frozen two-step gait probe."""
from __future__ import annotations
import json
import sys
from .freebase_worker import _apply_resource_limits, _run


def main() -> int:
    _apply_resource_limits()
    from .freebase_gait import SCENARIOS, MAX_STEPS
    try:
        if (len(sys.argv) != 5 or sys.argv[1] not in SCENARIOS or sys.argv[3] not in {'trace', 'summary'}
                or sys.argv[4] != '--confirmed-simulation'):
            raise ValueError('invalid internal gait probe arguments')
        steps = int(sys.argv[2])
        if not 1 <= steps <= MAX_STEPS:
            raise ValueError('invalid internal gait probe step budget')
        result = _run(sys.argv[1], steps, sys.argv[3] == 'trace', confirm_simulation=True,
                      controller='contact_gait')
        print(json.dumps(result, allow_nan=False))
        return 0
    except (ImportError, RuntimeError, ValueError, MemoryError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
