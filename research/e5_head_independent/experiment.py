"""Offline frozen-encoder classifier experiment, never a runtime policy."""
import argparse, hashlib, json, os, resource, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'protocol.json').read_text()); LABELS=P['labels']
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(name): return json.loads((ROOT/name).read_text())
def validate(rows, train=False):
    ids=set()
    for r in rows:
        assert set(r)=={'id','family','language','text','label'}
        assert r['id'] not in ids and r['language'] in ('en','hi','gu')
        assert isinstance(r['text'],str) and 0<len(r['text'])<=4096
        assert r['label'] in LABELS or (r['label'] is None and not train)
        ids.add(r['id'])
def split_check(a,b):
    assert not ({r['id'] for r in a}&{r['id'] for r in b})
    assert not ({r['family'] for r in a}&{r['family'] for r in b})
    assert not ({r['text'].strip().casefold() for r in a}&{r['text'].strip().casefold() for r in b})
def softmax(z):
    z=z-z.max(axis=1,keepdims=True); e=np.exp(z);return e/e.sum(axis=1,keepdims=True)
def fit(x,rows):
    w=np.zeros((x.shape[1],len(LABELS)),dtype=np.float64);b=np.zeros(len(LABELS))
    y=np.eye(len(LABELS))[[LABELS.index(r['label']) for r in rows]]
    loss=[]
    for i in range(P['steps']):
        q=softmax(x@w+b);g=(q-y)/len(rows)
        if i in (0,P['steps']-1):loss.append(float(-(y*np.log(q+1e-15)).sum()/len(rows)))
        w-=P['learning_rate']*(x.T@g+P['l2']*w);b-=P['learning_rate']*g.sum(axis=0)
    return w,b,loss
def evaluate(prob,rows,cutoff):
    out=[]
    for q,r in zip(prob,rows):
        ix=np.argsort(-q,kind='stable');score=float(q[ix[0]]);margin=float(q[ix[0]]-q[ix[1]])
        pred=LABELS[ix[0]] if score>=cutoff[0] and margin>=cutoff[1] else None
        out.append({'id':r['id'],'language':r['language'],'expected':r['label'],'selected':pred,'score':score,'margin':margin})
    def counts(rs):
        return {'total':len(rs),'known':sum(r['expected'] is not None for r in rs),'correct_known_accepts':sum(r['expected'] is not None and r['selected']==r['expected'] for r in rs),'wrong_known_accepts':sum(r['expected'] is not None and r['selected'] is not None and r['selected']!=r['expected'] for r in rs),'unsupported_false_accepts':sum(r['expected'] is None and r['selected'] is not None for r in rs),'abstentions':sum(r['selected'] is None for r in rs),'correct_decisions':sum(r['selected']==r['expected'] for r in rs)}
    return {'overall':counts(out),'per_language':{lang:counts([r for r in out if r['language']==lang]) for lang in ('en','hi','gu')},'predictions':out}
def tune(prob,rows):
    opts=[]
    for a in P['score_thresholds']:
        for b in P['margin_thresholds']:
            c=evaluate(prob,rows,(a,b))['overall']; opts.append(((c['wrong_known_accepts']+c['unsupported_false_accepts'],-c['correct_known_accepts'],-a,-b),(a,b)))
    return min(opts)[1]
def encode(rows,model_path):
    import torch
    from transformers import AutoTokenizer,AutoModel
    torch.set_num_threads(P['threads']);torch.manual_seed(P['seed'])
    tok=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    model=AutoModel.from_pretrained(model_path,local_files_only=True,trust_remote_code=False,use_safetensors=True).eval()
    for param in model.parameters():param.requires_grad_(False)
    out=[]
    with torch.inference_mode():
        for i in range(0,len(rows),P['batch_size']):
            batch=tok(['query: '+r['text'] for r in rows[i:i+P['batch_size']]],max_length=P['max_tokens'],padding=True,truncation=True,return_tensors='pt')
            h=model(**batch).last_hidden_state;mask=batch['attention_mask'].unsqueeze(-1)
            vec=(h*mask).sum(dim=1)/mask.sum(dim=1);vec=torch.nn.functional.normalize(vec,p=2,dim=1)
            out.append(vec.numpy().astype(np.float64))
    return np.concatenate(out)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);ap.add_argument('--heldout',action='store_true');args=ap.parse_args()
    start=time.monotonic()
    for name,sha in read('freeze.json').items():assert digest(ROOT/name)==sha,name
    train,dev=read('train.json'),read('dev.json');validate(train,True);validate(dev);split_check(train,dev)
    rows=train+dev
    if args.heldout:
        hold=read('heldout.json');validate(hold);split_check(train,hold);split_check(dev,hold);rows+=hold
    x=encode(rows,args.model_path); n=len(train);m=n+len(dev)
    w,b,loss=fit(x[:n],train);cutoff=tune(softmax(x[n:m]@w+b),dev)
    # Frozen cosine class centroids; cosine scores are not probabilities.
    proto=np.stack([x[:n][[r['label']==label for r in train]].mean(axis=0) for label in LABELS]);proto/=np.linalg.norm(proto,axis=1,keepdims=True)
    pc=tune(x[n:m]@proto.T,dev)
    report={'model':P['model'],'revision':P['revision'],'encoder_frozen':True,'optimizer_updates':P['steps'],'training_loss_initial_final_preupdate':loss,'cutoff':cutoff,'prototype_cutoff':pc,'dev':evaluate(softmax(x[n:m]@w+b),dev,cutoff),'prototype_dev':evaluate(x[n:m]@proto.T,dev,pc),'dataset_sha256':{name:digest(ROOT/name) for name in ['train.json','dev.json']},'promotion':False}
    if args.heldout:
        report['heldout']=evaluate(softmax(x[m:]@w+b),hold,cutoff);report['prototype_heldout']=evaluate(x[m:]@proto.T,hold,pc);report['dataset_sha256']['heldout.json']=digest(ROOT/'heldout.json')
    report['resources']={'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':P['threads']}
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
