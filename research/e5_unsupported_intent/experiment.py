"""Synthetic seven-class supported-intent probe; not production policy."""
import argparse,hashlib,importlib.util,json,resource,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'e5_head_independent'
spec=importlib.util.spec_from_file_location('frozen_encoder',BASE/'experiment.py')
encoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(encoder)
P=json.loads((ROOT/'protocol.json').read_text());LABELS=P['labels'];LANGS=('en','hi','gu')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(n):return json.loads((ROOT/n).read_text())
def validate(rows,train=False):
    ids=set();texts=set()
    for r in rows:
        assert set(r)=={'id','family','language','text','label'}
        assert r['language'] in LANGS and isinstance(r['text'],str) and 0<len(r['text'])<=4096
        assert r['label'] in LABELS if train else r['label'] in LABELS[:-1] or r['label'] is None
        norm=' '.join(r['text'].casefold().split());assert r['id'] not in ids and norm not in texts
        ids.add(r['id']);texts.add(norm)
def split(a,b):
    for key in ('id','family'):
        assert not ({r[key] for r in a}&{r[key] for r in b})
    assert not ({' '.join(r['text'].casefold().split()) for r in a}&{' '.join(r['text'].casefold().split()) for r in b})
def softmax(z):
    z=z-z.max(axis=1,keepdims=True);q=np.exp(z);return q/q.sum(axis=1,keepdims=True)
def centered(train,all_rows):
    mean=train.mean(axis=0);z=all_rows-mean;n=np.linalg.norm(z,axis=1,keepdims=True)
    if np.any(n<1e-12):raise ValueError('zero centered vector')
    return z/n,mean
def fit(x,rows):
    w=np.zeros((x.shape[1],len(LABELS)),dtype=np.float64);b=np.zeros(len(LABELS));y=np.eye(len(LABELS))[[LABELS.index(r['label']) for r in rows]];loss=[]
    for i in range(P['steps']):
        q=softmax(x@w+b);g=(q-y)/len(rows)
        if i in (0,P['steps']-1):loss.append(float(-(y*np.log(q+1e-15)).sum()/len(rows)))
        w-=P['learning_rate']*(x.T@g+P['l2']*w);b-=P['learning_rate']*g.sum(axis=0)
    return w,b,loss
def evaluate(prob,rows,cut):
    out=[]
    for q,r in zip(prob,rows):
        idx=np.argsort(-q,kind='stable');top=LABELS[int(idx[0])];score=float(q[idx[0]]);margin=float(q[idx[0]]-q[idx[1]])
        pred=top if top!='unsupported' and score>=cut[0] and margin>=cut[1] else None
        out.append({'id':r['id'],'language':r['language'],'expected':r['label'],'top1':top,'selected':pred,'score':score,'margin':margin})
    def count(rs):return {'total':len(rs),'known':sum(r['expected'] is not None for r in rs),'correct_known_accepts':sum(r['expected'] is not None and r['expected']==r['selected'] for r in rs),'wrong_known_accepts':sum(r['expected'] is not None and r['selected'] is not None and r['selected']!=r['expected'] for r in rs),'unsupported_false_accepts':sum(r['expected'] is None and r['selected'] is not None for r in rs),'abstentions':sum(r['selected'] is None for r in rs),'top1_unsupported':sum(r['top1']=='unsupported' for r in rs),'correct_decisions':sum(r['expected']==r['selected'] for r in rs)}
    return {'overall':count(out),'per_language':{l:count([r for r in out if r['language']==l]) for l in LANGS},'predictions':out}
def tune(prob,rows):
    opts=[]
    for a in P['score_thresholds']:
        for b in P['margin_thresholds']:
            c=evaluate(prob,rows,(a,b))['overall'];opts.append(((c['wrong_known_accepts']+c['unsupported_false_accepts'],-c['correct_known_accepts'],-a,-b),(a,b)))
    return min(opts)[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);ap.add_argument('--heldout',action='store_true');a=ap.parse_args();start=time.monotonic()
    for name,d in load('freeze.json').items():assert sha(ROOT/name)==d,name
    assert sha(BASE/'experiment.py')=='f9e3fdbf30b4644161333b3017f23aca95df7f786049d94b189254bda9f08447'
    for name,data in json.loads((BASE/'model-files.json').read_text()).items():assert sha(Path(a.model_path)/name)==data['sha256'],name
    train,dev=load('train.json'),load('dev.json');validate(train,True);validate(dev);split(train,dev);rows=train+dev
    assert len(train)==60 and len(dev)==36
    if a.heldout:
        held=load('heldout.json');validate(held);split(train,held);split(dev,held);rows+=held
    raw=encoder.encode(rows,a.model_path);x,mean=centered(raw[:len(train)],raw);n=len(train);m=n+len(dev)
    w,b,loss=fit(x[:n],train);d=softmax(x[n:m]@w+b);cut=tune(d,dev)
    report={'scope':'Original synthetic advisory/unsupported-intent classifier research only, no private sources or runtime promotion.','encoder_frozen':True,'updates':P['steps'],'classes':LABELS,'loss_initial_final_preupdate':loss,'dev_selected_cutoff':cut,'dev':evaluate(d,dev,cut),'dataset_sha256':{n:sha(ROOT/n) for n in ['train.json','dev.json']},'train_mean_sha256':hashlib.sha256(mean.tobytes()).hexdigest(),'source_sha256':sha(__file__),'protocol_sha256':sha(ROOT/'protocol.json'),'promoted':False}
    if a.heldout:report['heldout']=evaluate(softmax(x[m:]@w+b),held,cut);report['dataset_sha256']['heldout.json']=sha(ROOT/'heldout.json')
    report['resources']={'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2}
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
