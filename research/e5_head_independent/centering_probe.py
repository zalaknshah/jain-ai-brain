"""Train-only centered embeddings. Old holdout is seen regression, not validation."""
import argparse,hashlib,json,resource,time
from pathlib import Path
import numpy as np
import experiment as base
ROOT=Path(__file__).resolve().parent

def center(train,all_rows):
    mean=train.mean(axis=0)
    z=all_rows-mean
    norms=np.linalg.norm(z,axis=1,keepdims=True)
    if np.any(norms<1e-12):raise ValueError('near-zero centered representation')
    return z/norms,mean

def train_report(x,train,dev,regression):
    n=len(train);m=n+len(dev)
    w,b,loss=base.fit(x[:n],train)
    d=base.softmax(x[n:m]@w+b);r=base.softmax(x[m:]@w+b)
    cut=base.tune(d,dev)
    return {'loss_initial_final_preupdate':loss,'dev_selected_cutoff':cut,'dev':base.evaluate(d,dev,cut),'seen_regression':base.evaluate(r,regression,cut),'known_top1_correct_before_abstention':sum(base.LABELS[int(np.argmax(q))]==row['label'] for q,row in zip(r,regression) if row['label'] is not None)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);a=ap.parse_args();start=time.monotonic()
    for name,sha in base.read('freeze.json').items():assert base.digest(ROOT/name)==sha
    train,dev,reg=[base.read(n+'.json') for n in ('train','dev','heldout')]
    base.validate(train,True);base.validate(dev);base.validate(reg)
    base.split_check(train,dev);base.split_check(train,reg);base.split_check(dev,reg)
    x=base.encode(train+dev+reg,a.model_path)
    z,mean=center(x[:len(train)],x)
    report={'scope':'Synthetic frozen-encoder/head research. Previously read holdout is seen regression only. No runtime promotion.','protocol_sha256':base.digest(ROOT/'centering-protocol.json'),'source_sha256':base.digest(__file__),'dataset_sha256':{name:base.digest(ROOT/name) for name in ['train.json','dev.json','heldout.json']},'train_mean_sha256':hashlib.sha256(mean.tobytes()).hexdigest(),'train_mean_norm':float(np.linalg.norm(mean)),'raw':train_report(x,train,dev,reg),'centered':train_report(z,train,dev,reg),'resources':{'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2},'promoted':False}
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
