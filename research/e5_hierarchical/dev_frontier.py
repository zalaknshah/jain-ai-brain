"""Post-run dev-only tradeoff summary. Does not select or change a model."""
import json
from pathlib import Path
from probe import P,sha
ROOT=Path(__file__).resolve().parent

def summarize(report):
 rows=report['dev']['predictions'];best={}
 for a in P['gate_thresholds']:
  for b in P['topic_thresholds']:
   for c in P['topic_margin_thresholds']:
    correct=false=0
    for r in rows:
     pred=r['top1_topic'] if r['support_probability']>=a and r['topic_probability']>=b and r['topic_margin']>=c else None
     correct+=r['expected'] is not None and pred==r['expected']
     false+=pred is not None and pred!=r['expected']
    if false not in best or correct>best[false]['correct_supported_accepts']:best[false]={'false_accepts':false,'correct_supported_accepts':correct}
 return {'scope':'Dev-only exploratory grid tradeoff. No policy change, no test data, no validation claim.','points':[best[x] for x in sorted(best)],'frozen_selected_cutoff':report['cutoff']}
if __name__=='__main__':
 r=json.loads((ROOT/'observed-report.json').read_text());out=summarize(r);out['source_report_sha256']=sha(ROOT/'observed-report.json');print(json.dumps(out,indent=2))
