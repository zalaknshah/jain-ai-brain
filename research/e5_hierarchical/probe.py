"""Hierarchical intent research, not robot policy or independent validation."""
import argparse,hashlib,importlib.util,json,resource,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;PRIOR=ROOT.parent/'e5_unsupported_intent';SEEN=ROOT.parent/'e5_generalization'
s=importlib.util.spec_from_file_location('old_intent',PRIOR/'experiment.py');old=importlib.util.module_from_spec(s);s.loader.exec_module(old)
P=json.loads((ROOT/'protocol.json').read_text());TOPICS=old.LABELS[:-1]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fit(x,y,classes):
 w=np.zeros((x.shape[1],classes),dtype=np.float64);b=np.zeros(classes);target=np.eye(classes)[y];loss=[]
 for i in range(P['steps_per_head']):
  q=old.softmax(x@w+b);g=(q-target)/len(x)
  if i in (0,P['steps_per_head']-1):loss.append(float(-(target*np.log(q+1e-15)).sum()/len(x)))
  w-=P['learning_rate']*(x.T@g+P['l2']*w);b-=P['learning_rate']*g.sum(axis=0)
 return w,b,loss
def evaluate(gates,topics,rows,cut):
 out=[]
 for gate,q,r in zip(gates,topics,rows):
  ix=np.argsort(-q,kind='stable');top=TOPICS[int(ix[0])];score=float(q[ix[0]]);margin=float(q[ix[0]]-q[ix[1]]);support=float(gate[1]);pred=top if support>=cut[0] and score>=cut[1] and margin>=cut[2] else None
  out.append({'id':r['id'],'language':r['language'],'expected':r['label'],'selected':pred,'support_probability':support,'top1_topic':top,'topic_probability':score,'topic_margin':margin})
 def count(rs):return {'total':len(rs),'known':sum(r['expected'] is not None for r in rs),'correct_known_accepts':sum(r['expected'] is not None and r['selected']==r['expected'] for r in rs),'wrong_known_accepts':sum(r['expected'] is not None and r['selected'] is not None and r['selected']!=r['expected'] for r in rs),'unsupported_false_accepts':sum(r['expected'] is None and r['selected'] is not None for r in rs),'abstentions':sum(r['selected'] is None for r in rs)}
 return {'overall':count(out),'per_language':{l:count([r for r in out if r['language']==l]) for l in old.LANGS},'predictions':out}
def tune(g,t,rows):
 options=[]
 for a in P['gate_thresholds']:
  for b in P['topic_thresholds']:
   for c in P['topic_margin_thresholds']:
    m=evaluate(g,t,rows,(a,b,c))['overall'];options.append(((m['wrong_known_accepts']+m['unsupported_false_accepts'],-m['correct_known_accepts'],-a,-b,-c),(a,b,c)))
 return min(options)[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);a=ap.parse_args();start=time.monotonic()
 for directory in [ROOT,PRIOR]:
  for name,d in read(directory/'freeze.json').items():assert sha(directory/name)==d
 for name,data in read(old.BASE/'model-files.json').items():assert sha(Path(a.model_path)/name)==data['sha256']
 train,dev,seen=[read(p) for p in [PRIOR/'train.json',PRIOR/'dev.json',SEEN/'heldout.json']]
 old.validate(train,True);old.validate(dev);old.validate(seen);old.split(train,seen);old.split(dev,seen)
 n=len(train);m=n+len(dev);raw=old.encoder.encode(train+dev+seen,a.model_path);x,mean=old.centered(raw[:n],raw)
 gy=[int(r['label']!='unsupported') for r in train];mask=np.array(gy,dtype=bool);ty=[TOPICS.index(r['label']) for r in train if r['label']!='unsupported']
 gw,gb,gloss=fit(x[:n],gy,2);tw,tb,tloss=fit(x[:n][mask],ty,6)
 g=old.softmax(x@gw+gb);t=old.softmax(x@tw+tb);cut=tune(g[n:m],t[n:m],dev)
 report={'scope':'Architectural probe on previously seen regression. Not independent validation, model promotion or brain qualification.','protocol_sha256':sha(ROOT/'protocol.json'),'source_sha256':sha(__file__),'dataset_sha256':{'train':sha(PRIOR/'train.json'),'dev':sha(PRIOR/'dev.json'),'seen_regression':sha(SEEN/'heldout.json')},'train_mean_sha256':hashlib.sha256(mean.tobytes()).hexdigest(),'head_sha256':hashlib.sha256(gw.tobytes()+gb.tobytes()+tw.tobytes()+tb.tobytes()).hexdigest(),'gate_loss_initial_final':gloss,'topic_loss_initial_final':tloss,'cutoff':cut,'dev':evaluate(g[n:m],t[n:m],dev,cut),'seen_regression':evaluate(g[m:],t[m:],seen,cut),'promoted':False,'resources':{'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2}}
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
