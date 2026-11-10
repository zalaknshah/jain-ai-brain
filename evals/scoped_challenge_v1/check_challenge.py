#!/usr/bin/env python3
"""Check saved trace rows against frozen authored expectations; never execute candidate."""
import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('trace',nargs='+');p.add_argument('--corpus',default=str(pathlib.Path(__file__).with_name('challenge.json')));a=p.parse_args()
gold=json.loads(pathlib.Path(a.corpus).read_text())['cases'];seen={};errors=[]
for f in a.trace:
 t=json.loads(pathlib.Path(f).read_text())
 for row in t['cases']:
  if row['case_id'] in seen: errors.append('duplicate '+row['case_id'])
  seen[row['case_id']]=row
for g in gold:
 cid=g['input']['id'];r=seen.get(cid)
 if r is None: errors.append('missing '+cid);continue
 checks=[{'path':[k],'value':g['expected'][k]} for k in ('label','reason')]+g['expected']['checks']
 for c in checks:
  try:
   v=r
   for key in c['path']:v=v[key]
   # Compare canonical serialized forms: bools are not integers, and extra keys differ.
   if json.dumps(v,sort_keys=True,separators=(',',':'))!=json.dumps(c['value'],sort_keys=True,separators=(',',':')):raise ValueError('unequal')
  except (KeyError,IndexError,TypeError,ValueError):errors.append(cid+' '+json.dumps(c['path'])+' mismatch')
extra=set(seen)-{g['input']['id'] for g in gold}
errors.extend('unexpected '+x for x in sorted(extra))
print(json.dumps({'case_count':len(gold),'checked_rows':len(seen),'errors':errors},indent=2))
sys.exit(bool(errors))
