"""New synthetic evaluation of unchanged prior classifier, without test tuning."""
import argparse,collections,hashlib,importlib.util,json,resource,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parent/'e5_unsupported_intent'
spec=importlib.util.spec_from_file_location('frozen_intent',PRIOR/'experiment.py')
frozen=importlib.util.module_from_spec(spec);spec.loader.exec_module(frozen)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def validate_test(rows):
 frozen.validate(rows)
 if len(rows)!=72:raise ValueError('require72 rows')
 groups=collections.defaultdict(list)
 for r in rows:groups[r['family']].append(r)
 if len(groups)!=24:raise ValueError('require24 families')
 labels=[]
 for name,rs in groups.items():
  if len(rs)!=3 or {r['language'] for r in rs}!={'en','hi','gu'}:raise ValueError('family needs matched languages')
  if len({r['label'] for r in rs})!=1:raise ValueError('family label mismatch')
  labels.append(rs[0]['label'])
 counts=collections.Counter(labels)
 if counts[None]!=12 or any(counts[x]!=2 for x in frozen.LABELS[:-1]):raise ValueError('incorrect family label balance')
 return groups

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);a=ap.parse_args();start=time.monotonic()
 for name,d in read(ROOT/'freeze.json').items():assert sha(ROOT/name)==d,name
 for name,d in read(PRIOR/'freeze.json').items():assert sha(PRIOR/name)==d,name
 for name,data in read(frozen.BASE/'model-files.json').items():assert sha(Path(a.model_path)/name)==data['sha256'],name
 train,dev,held=[read(p) for p in [PRIOR/'train.json',PRIOR/'dev.json',ROOT/'heldout.json']]
 frozen.validate(train,True);frozen.validate(dev);groups=validate_test(held)
 for previous in [train,dev,read(PRIOR/'heldout.json'),read(frozen.BASE/'heldout.json')]:frozen.split(previous,held)
 raw=frozen.encoder.encode(train+dev+held,a.model_path);x,mean=frozen.centered(raw[:len(train)],raw);n=len(train);m=n+len(dev)
 w,b,loss=frozen.fit(x[:n],train);d=frozen.softmax(x[n:m]@w+b);cut=frozen.tune(d,dev)
 assert tuple(cut)==(0,.1)
 dev_result=frozen.evaluate(d,dev,cut);assert dev_result==read(PRIOR/'dev-report.json')['dev'],'prior dev changed'
 result=frozen.evaluate(frozen.softmax(x[m:]@w+b),held,cut);byid={r['id']:r for r in result['predictions']};family=[]
 for name,rs in groups.items():
  pred=[byid[r['id']] for r in rs];known=rs[0]['label'] is not None
  family.append({'family':name,'expected':rs[0]['label'],'correct_languages':sum(r['selected']==r['expected'] for r in pred),'supported_accepted_languages':sum(known and r['selected']==r['expected'] for r in pred),'unsupported_false_accept_languages':sum(not known and r['selected'] is not None for r in pred)})
 summary={'families':24,'supported_families':12,'unsupported_families':12,'supported_families_all3_correct':sum(r['expected'] is not None and r['correct_languages']==3 for r in family),'unsupported_families_any_false_accept':sum(r['expected'] is None and r['unsupported_false_accept_languages']>0 for r in family)}
 from transformers import AutoTokenizer
 tok=AutoTokenizer.from_pretrained(a.model_path,local_files_only=True,trust_remote_code=False)
 lengths=[len(tok('query: '+r['text'])['input_ids']) for r in held]
 report={'scope':'Frozen previous trained head on fresh independent synthetic scenario families, not model improvement or robot qualification.','prior_code_sha256':sha(PRIOR/'experiment.py'),'source_sha256':sha(__file__),'protocol_sha256':sha(ROOT/'protocol.json'),'new_test_sha256':sha(ROOT/'heldout.json'),'unchanged_prior_test_sha256':sha(PRIOR/'heldout.json'),'train_sha256':sha(PRIOR/'train.json'),'dev_sha256':sha(PRIOR/'dev.json'),'head_sha256':hashlib.sha256(w.tobytes()+b.tobytes()).hexdigest(),'train_mean_sha256':hashlib.sha256(mean.tobytes()).hexdigest(),'dev_exactly_matches_prior':True,'dev_cutoff':cut,'test':result,'family_summary':summary,'families':family,'token_lengths':{'maximum':max(lengths),'truncated_rows':sum(n>128 for n in lengths)},'promoted':False,'resources':{'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2}}
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
