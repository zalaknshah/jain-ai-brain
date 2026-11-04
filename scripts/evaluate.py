"""Run the checked-in regression cases without a model or network."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jace.engine import CognitiveEngine  # noqa: E402
from jace.reasoner import LocalReasoner  # noqa: E402


def main() -> int:
    cases = [json.loads(line) for name in ("safety_cases.jsonl", "practical_cases.jsonl")
             for line in (ROOT / "evals" / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        engine = CognitiveEngine(db_path=Path(directory) / "evaluation.sqlite3", canonical_path="", reasoner=LocalReasoner())
        try:
            for case in cases:
                result = engine.think("evaluation-user", case["input"])
                actual_allowed = result.ethical_assessment.allowed
                actual_action = result.action.action if result.action else None
                if actual_allowed != case["allowed"] or actual_action != case["action"] or len(result.perspectives) != 7:
                    failures.append(f"{case['id']}: allowed={actual_allowed}, action={actual_action}, perspectives={len(result.perspectives)}")
                for phrase in case.get("contains", []):
                    if phrase not in result.response:
                        failures.append(f"{case['id']}: missing required response phrase {phrase!r}")
        finally:
            engine.close()
    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1
    print(f"PASS: {len(cases)} evaluation cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
