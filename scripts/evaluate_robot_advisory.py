"""Collect local synthetic advisory outputs for later qualified human review."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from robot_advisory_eval import collect_local, summarize

if __name__ == '__main__':
    cases = json.loads((ROOT / 'evals/robot_advisory/cases.json').read_text(encoding='utf-8'))
    outputs = collect_local(cases)
    print(json.dumps({'report': summarize(cases, outputs), 'outputs': outputs}, ensure_ascii=True, indent=2))
