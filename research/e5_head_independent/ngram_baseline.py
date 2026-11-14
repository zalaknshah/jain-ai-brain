"""Synthetic Unicode n-gram routing research. Not a runtime or robot policy."""
import collections
import hashlib
import json
import math
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parent
LABELS = ('noninjury', 'restraint', 'perspectives', 'conditional', 'provenance', 'consent')
LANGS = ('en', 'hi', 'gu')

def features(text):
    # Keep combining marks; ASCII-only regexes silently discard Indic scripts.
    text = ' '.join(unicodedata.normalize('NFC', text).casefold().split())
    if not text or len(text) > 4096:
        raise ValueError('query must contain 1..4096 characters')
    s = ' ' + text + ' '
    counts = collections.Counter(s[i:i+n] for n in (3,4,5) for i in range(len(s)-n+1))
    return counts

def norm(v):
    length = math.sqrt(sum(x*x for x in v.values()))
    return {k:x/length for k,x in v.items()} if length else {}

def fit(rows, english_only=False):
    groups = collections.defaultdict(collections.Counter)
    for row in rows:
        if row['label'] not in LABELS or row['language'] not in LANGS:
            raise ValueError('invalid training label/language')
        if english_only and row['language'] != 'en':
            continue
        groups[(row['label'],row['language'])].update(norm(features(row['text'])))
    return {key:norm(value) for key,value in groups.items()}

def scores(model, text):
    q = norm(features(text))
    # Language prototypes share decision labels, not a learned semantic space.
    best = {label:0.0 for label in LABELS}
    for (label,_), prototype in model.items():
        best[label] = max(best[label], sum(v*prototype.get(k,0) for k,v in q.items()))
    rank = sorted(best, key=lambda label:(-best[label],label))
    return rank[0],best[rank[0]],best[rank[0]]-best[rank[1]]

def predict(model, text, threshold):
    label,score,margin = scores(model,text)
    return label if score >= threshold[0] and margin >= threshold[1] else None

def evaluate(model, rows, threshold):
    records = [{**r,'selected':predict(model,r['text'],threshold)} for r in rows]
    def metrics(items):
        return {'count':len(items),'known':sum(r['label'] is not None for r in items),
          'correct_known_accepts':sum(r['label'] is not None and r['label']==r['selected'] for r in items),
          'wrong_known_accepts':sum(r['label'] is not None and r['selected'] is not None and r['label']!=r['selected'] for r in items),
          'unknown_false_accepts':sum(r['label'] is None and r['selected'] is not None for r in items),
          'abstentions':sum(r['selected'] is None for r in items),
          'correct_decisions':sum(r['label']==r['selected'] for r in items)}
    return {'overall':metrics(records),'languages':{l:metrics([r for r in records if r['language']==l]) for l in LANGS},'cases':records}

def calibrate(model, dev):
    candidates=[]
    for score in (0.10,0.20,0.30,0.40,0.50,0.60):
        for margin in (0.05,0.10,0.20):
            m=evaluate(model,dev,(score,margin))['overall']
            # False accepts dominate known coverage. Ties prefer more conservative cutoffs.
            key=(m['unknown_false_accepts']+m['wrong_known_accepts'],-m['correct_known_accepts'],-score,-margin)
            candidates.append((key,(score,margin)))
    return min(candidates)[1]

def load(name):
    return json.loads((ROOT/name).read_text())

def validate_splits(*splits):
    ids=set(); texts=set(); families=set()
    for rows in splits:
        local_families=set()
        for row in rows:
            if set(row)!={'id','family','language','text','label'} or row['language'] not in LANGS or row['label'] not in (*LABELS,None):
                raise ValueError('invalid case')
            f=' '.join(unicodedata.normalize('NFC',row['text']).casefold().split())
            if row['id'] in ids or f in texts or row['family'] in families:
                raise ValueError('cross-split leakage or duplicate')
            ids.add(row['id']); texts.add(f); local_families.add(row['family'])
        families.update(local_families)

def main():
    train,dev,heldout=[load(x+'.json') for x in ('train','dev','heldout')]
    validate_splits(train,dev,heldout)
    report={'scope':'Synthetic same-author unreviewed translation drafts. No scripture, runtime promotion, robot qualification, private data or exported weights.',
            'split_sha256':{x:hashlib.sha256((ROOT/(x+'.json')).read_bytes()).hexdigest() for x in ('train','dev','heldout')}, 'methods':{}}
    for name,english in [('english_only',True),('multilingual_prototypes',False)]:
        model=fit(train,english); threshold=calibrate(model,dev)
        report['methods'][name]={'threshold':threshold,'dev':evaluate(model,dev,threshold),'heldout':evaluate(model,heldout,threshold)}
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=='__main__': main()
