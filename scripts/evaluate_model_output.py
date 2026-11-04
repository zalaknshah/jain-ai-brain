"""Offline mechanical citation regressions, not a model-quality benchmark."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.models import CanonicalEntry
from jace.model_output import check_model_output


def main() -> int:
    cases = [json.loads(line) for line in (ROOT/'evals/model_output_cases.jsonl').read_text().splitlines() if line.strip()]
    results, failures = [], []
    for case in cases:
        passage = 'આ વાક્ય માત્ર પરીક્ષણ માટે છે.' if case.get('unicode') else 'Inspect the synthetic area and choose a reversible next step.'
        entry = CanonicalEntry('fixture:one','Original synthetic test',passage,'Synthetic interpretation only.',
                               'Original fixture, not a Jain source',work='Synthetic test work',language='gu' if case.get('unicode') else 'en',
                               location='fixture line 1',license='MIT',verified=case['reviewed'])
        try:
            result = check_model_output(json.dumps(case['content'],ensure_ascii=False),[entry])
            accepted = True
            if 'not independently verified' not in result.render():
                failures.append(case['id']+': missing answer qualification')
            if result.citations and 'does not establish' not in result.render():
                failures.append(case['id']+': missing entailment qualification')
        except ValueError:
            accepted = False
        if accepted != case['accepted']:
            failures.append(case['id']+': unexpected admission result')
        results.append({'id':case['id'],'accepted':accepted,'expected':case['accepted']})
    print(json.dumps({'fixture_assertions_passed':not failures,'cases':len(cases),'failures':failures,'results':results,
                      'scope':'Mechanical source identity and exact-text checks on original synthetic fixtures; no actual model or scholarly corpus evaluation.'},indent=2))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
