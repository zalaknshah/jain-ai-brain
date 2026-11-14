"""Evaluate unchanged earlier heads against this fresh set; never refit on it."""
import argparse,json,resource,time
from pathlib import Path
import numpy as np
import experiment as new
old=new.encoder

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);a=ap.parse_args();start=time.monotonic()
 for name,data in json.loads((new.BASE/'model-files.json').read_text()).items():assert new.sha(Path(a.model_path)/name)==data['sha256'],name
 train,dev=[json.loads((new.BASE/n).read_text()) for n in ('train.json','dev.json')];held=new.load('heldout.json')
 old.validate(train,True);old.validate(dev);old.validate(held);old.split_check(train,held);old.split_check(dev,held)
 x=old.encode(train+dev+held,a.model_path);n=len(train);m=n+len(dev);z,_=new.centered(x[:n],x)
 report={'scope':'Unchanged earlier raw and centered six-class heads on the same new independent test, trained/calibrated on their original train/dev only. No test tuning. New seven-class system also changes dataset richness; not an isolated causal ablation.','dataset_sha256':{'old_train':new.sha(new.BASE/'train.json'),'old_dev':new.sha(new.BASE/'dev.json'),'fresh_heldout':new.sha(new.ROOT/'heldout.json')},'methods':{}}
 for name,vectors in [('old_raw',x),('old_centered',z)]:
  w,b,loss=old.fit(vectors[:n],train);d=old.softmax(vectors[n:m]@w+b);cut=old.tune(d,dev)
  report['methods'][name]={'dev_cutoff':cut,'dev':old.evaluate(d,dev,cut),'heldout':old.evaluate(old.softmax(vectors[m:]@w+b),held,cut)}
 report['resources']={'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2}
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
