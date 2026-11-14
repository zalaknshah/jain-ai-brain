"""Small generative CPU dev feasibility; no model training or action interface."""
import argparse,hashlib,json,resource,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
P=json.loads((ROOT/'protocol.json').read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def grade(text,expected,rule):
 try:
  x=json.loads(text)
 except (ValueError,TypeError):return {'schema_valid':False,'decision_rule_match':False}
 valid=isinstance(x,dict) and set(x)=={'decision','rule','reason'} and x['decision'] in ('advise','abstain') and x['rule'] in ('R0','R1') and isinstance(x['reason'],str) and 0<len(x['reason'])<=1000
 return {'schema_valid':valid,'decision_rule_match':bool(valid and x['decision']==expected and x['rule']==rule)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model-path',required=True);a=ap.parse_args();start=time.monotonic()
 for n,d in json.loads((ROOT/'freeze.json').read_text()).items():assert sha(ROOT/n)==d,n
 for n,d in json.loads((ROOT/'model-files.json').read_text()).items():assert sha(Path(a.model_path)/n)==d['sha256'],n
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer
 torch.set_num_threads(2);torch.manual_seed(173)
 tok=AutoTokenizer.from_pretrained(a.model_path,local_files_only=True,trust_remote_code=False)
 model=AutoModelForCausalLM.from_pretrained(a.model_path,local_files_only=True,trust_remote_code=False,use_safetensors=True,torch_dtype=torch.float32).eval()
 loaded=time.monotonic();rows=json.loads((ROOT/'dev.json').read_text());assert len(rows)==6;out=[]
 for row in rows:
  messages=[{'role':'system','content':(ROOT/'system.txt').read_text()},{'role':'user','content':row['prompt']}]
  text=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
  inp=tok(text,return_tensors='pt');assert inp.input_ids.shape[1]<=P['max_input_tokens']
  t=time.monotonic()
  with torch.inference_mode():
   seq=model.generate(**inp,max_new_tokens=P['max_new_tokens'],max_time=P['max_seconds_per_case'],do_sample=False,pad_token_id=tok.eos_token_id)
  raw=tok.decode(seq[0,inp.input_ids.shape[1]:],skip_special_tokens=True).strip()
  elapsed=time.monotonic()-t;item={'id':row['id'],'language':row['language'],'expected':row['expected'],'expected_rule':row['rule'],'output':raw,'grade':grade(raw,row['expected'],row['rule']),'new_tokens':int(seq.shape[1]-inp.input_ids.shape[1]),'input_tokens':int(inp.input_ids.shape[1]),'wall_seconds':elapsed}
  out.append(item)
  print(json.dumps({'case_completed':row['id'],'new_tokens':item['new_tokens'],'wall_seconds':elapsed}),flush=True)
 result={'scope':'Same-author synthetic dev feasibility only, two scenario families, no independent validation or model training.','model':P['model'],'revision':P['revision'],'cases':out,'summary':{'schema_valid':sum(x['grade']['schema_valid'] for x in out),'decision_rule_match':sum(x['grade']['decision_rule_match'] for x in out),'total':len(out)},'semantic_or_language_quality_automatically_proved':False,'promoted':False,'source_sha256':sha(__file__),'protocol_sha256':sha(ROOT/'protocol.json'),'dataset_sha256':sha(ROOT/'dev.json'),'resources':{'load_seconds':loaded-start,'wall_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'threads':2}}
 (ROOT/'observed-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result['summary']),flush=True)
if __name__=='__main__':main()
