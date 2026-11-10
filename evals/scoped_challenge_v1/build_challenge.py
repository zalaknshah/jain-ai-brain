#!/usr/bin/env python3
"""Contract-only authored scenarios. Expected labels are stipulations, not solver output."""
import json, hashlib, pathlib
D=pathlib.Path(__file__).resolve().parent
C=[]
def canon(o): return json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def add(name, passages, claim, label, why, checks=None, reason=None, details=None):
    if isinstance(passages,str): passages=[passages]
    ps=[{'id':f'p{i+1}','text':p} for i,p in enumerate(passages)]
    case={'id':name,'passages':ps,'claim':claim,'citations':[{'passage_id':'p1','quote':passages[0][:min(40,len(passages[0]))]}]}
    # Citations deliberately cite only the first passage; all passages remain premises.
    if reason is None: reason='direct_assertion_membership' if claim.strip().startswith(('Asserts','Not-asserts')) else ('relevant_inconsistent_context' if label=='abstain' else 'complete_component_check')
    expected={'label':label,'reason':reason,'details':details or {},'checks':checks or {}}
    if reason not in ('direct_assertion_membership','complete_component_check','relevant_inconsistent_context'):
        expected['checks'].update({x:None for x in ['query','counts','symbols','records','references','diagnostics','evaluation']})
    else: expected['checks']['diagnostics.scan_complete']=True
    C.append({'case':case,'expected':expected,'rationale':why})
K='scribe/v1/page'; O='other/v1/page'
def fact(sign=False,obj='Ada',prop='amber'): return f'Object {obj} is '+('not ' if sign else '')+prop
# 48 direct membership tests: presence vs opposite vs derived vs another scope.
for typ,body,present in [
 ('direct','Report '+K+'#a dawn: Object Ada is amber.',True),
 ('opposite','Report '+K+'#a dawn: Object Ada is not amber.',False),
 ('derived','Report '+K+'#a dawn: Object Ada is blue.Report '+K+'#b dawn: Every blue object is amber.',False),
 ('world','World dawn: Object Ada is amber.',False),
 ('other_frame','Report '+K+'#a dusk: Object Ada is amber.',False),
 ('other_version','Report scribe/v2/page#a dawn: Object Ada is amber.',False),
 ('other_extent','Report scribe/v1/whole#a dawn: Object Ada is amber.',False),
 ('other_source','Report '+O+'#a dawn: Object Ada is amber.',False),
 ('both','Report '+K+'#a dawn: Object Ada is amber.Report '+K+'#b dawn: Object Ada is not amber.',True),
 ('duplicate','Report '+K+'#a dawn: Object Ada is amber.Report '+K+'#a dawn: Object Ada is amber.',True),
 ('other_entity','Report '+K+'#a dawn: Object Bea is amber.',False),
 ('empty','World dawn: Object Bea is blue.',False)]:
 for closed in (False,True):
  for outer in (False,True):
   label=('supported' if present else ('contradicted' if closed else 'not_established'))
   if outer: label={'supported':'contradicted','contradicted':'supported','not_established':'not_established'}[label]
   add(f'membership_{typ}_{int(closed)}_{int(outer)}',body+('Complete '+K+'.' if closed else ''),('Not-asserts' if outer else 'Asserts')+f' {K} dawn: Object Ada is amber.',label,
       f'{typ}: only an exact directly reported atomic fact counts. Completeness is {closed}; outer membership negation is {outer}.',{'evaluation.present':present,'evaluation.complete':closed,'evaluation.outer_negated':outer})
# Classical deductions and deliberately syntactic component policy: 34 sign-paired cases.
logic=[
 ('positive','World dawn: Object Ada is amber.','amber','supported',['amber'],[True],None),
 ('negative','World dawn: Object Ada is not amber.','amber','contradicted',['amber'],None,[False]),
 ('unknown','World dawn: Object Ada is blue.','amber','not_established',['amber'],[True],[False]),
 ('implication','World dawn: Object Ada is amber.World dawn: Every amber object is blue.','blue','supported',['amber','blue'],[True,True],None),
 ('contraposition','World dawn: Object Ada is not blue.World dawn: Every amber object is blue.','amber','contradicted',['amber','blue'],None,[False,False]),
 ('no_converse','World dawn: Object Ada is blue.World dawn: Every amber object is blue.','amber','not_established',['amber','blue'],[True,True],[False,True]),
 ('exclusion','World dawn: Object Ada is amber.World dawn: No amber object is blue.','blue','contradicted',['amber','blue'],None,[True,False]),
 ('exclusion_reverse','World dawn: Object Ada is blue.World dawn: Every amber object is not blue.','amber','contradicted',['amber','blue'],None,[False,True]),
 ('no_import','World dawn: Every amber object is blue.','blue','not_established',['amber','blue'],[False,True],[False,False]),
 ('positive_self','World dawn: Every amber object is amber.','amber','not_established',['amber'],[True],[False]),
 ('negative_self','World dawn: No amber object is amber.','amber','contradicted',['amber'],None,[False]),
 ('rule_only_forcing','World dawn: Every amber object is blue.World dawn: Every blue object is not amber.','amber','contradicted',['amber','blue'],None,[False,False]),
 ('same_entity_conflict','World dawn: Object Ada is amber.World dawn: Object Ada is not amber.','amber','abstain',['amber'],None,None),
 ('other_entity_conflict','World dawn: Object Bea is amber.World dawn: Object Bea is not amber.World dawn: Object Ada is amber.','amber','supported',['amber'],[True],None),
 ('disconnected_conflict','World dawn: Object Ada is blue.World dawn: Object Ada is not blue.World dawn: Object Ada is amber.','amber','supported',['amber'],[True],None),
 ('redundant_connector','World dawn: Object Ada is blue.World dawn: Object Ada is not blue.World dawn: Object Ada is amber.World dawn: Every blue object is amber.','amber','abstain',['amber','blue'],None,None),
 ('frame_conflict','World dusk: Object Ada is amber.World dusk: Object Ada is not amber.World dawn: Object Ada is amber.','amber','supported',['amber'],[True],None)]
for name,p,prop,label,component,tw,fw in logic:
 for neg in (False,True):
  lab=({'supported':'contradicted','contradicted':'supported'}.get(label,label) if neg else label)
  a,b=(fw,tw) if neg else (tw,fw)
  add('logic_'+name+'_'+str(int(neg)),p,'World dawn: '+fact(neg,prop=prop)+'.',lab,
      f'{name}: apply material implication in the query object and predicate component only. Negative query swaps witness roles, not the theory.',
      {'evaluation.component':component,'evaluation.true_witness':a,'evaluation.false_witness':b,'evaluation.true_possible':a is not None,'evaluation.false_possible':b is not None,'evaluation.satisfiable':label!='abstain'})
# 24 scope and bridge tests, each with both query signs.
scope=[
 ('report_not_world',f'Report {K}#a dawn: Object Ada is amber.','World dawn: ','not_established'),
 ('fact_bridge',f'True {K}#a.Report {K}#a dawn: Object Ada is amber.','World dawn: ','supported'),
 ('rule_bridge',f'World dawn: Object Ada is blue.Report {K}#a dawn: Every blue object is amber.True {K}#a.','World dawn: ','supported'),
 ('only_one_entry',f'Report {K}#a dawn: Object Ada is blue.Report {K}#b dawn: Object Ada is amber.True {K}#a.','World dawn: ','not_established'),
 ('only_one_version',f'Report scribe/v2/page#a dawn: Object Ada is amber.Report {K}#a dawn: Object Ada is blue.True {K}#a.','World dawn: ','not_established'),
 ('no_world_import',f'World dawn: Object Ada is amber.Report {K}#a dawn: Object Bea is blue.',f'Account [{K}] dawn: ','not_established'),
 ('no_truth_reverse',f'Report {O}#a dawn: Object Ada is amber.True {O}#a.Complete {K}.',f'Account [{K}] dawn: ','not_established'),
 ('no_complete_negation',f'Complete {K}.',f'Account [{K}] dawn: ','not_established'),
 ('combine_sources',f'Report {K}#a dawn: Object Ada is blue.Report {O}#a dawn: Every blue object is amber.',f'Account [{K},{O}] dawn: ','supported'),
 ('unselected_rule',f'Report {K}#a dawn: Object Ada is blue.Report {O}#a dawn: Every blue object is amber.',f'Account [{K}] dawn: ','not_established'),
 ('different_frame',f'Report {K}#a dusk: Object Ada is blue.Report {K}#b dawn: Every blue object is amber.',f'Account [{K}] dawn: ','not_established'),
 ('union_conflict',f'Report {K}#a dawn: Object Ada is amber.Report {O}#a dawn: Object Ada is not amber.',f'Account [{O},{K}] dawn: ','abstain')]
for name,p,prefix,label in scope:
 for neg in (False,True):
  lab={'supported':'contradicted','contradicted':'supported'}.get(label,label) if neg else label
  add('scope_'+name+'_'+str(int(neg)),p,prefix+fact(neg)+'.',lab,f'{name}: scope selection is exact; sign changes only the queried proposition.')
# Reference identity and provenance, not semantic equivalence.
add('reference_alias',f'Report {K}#a dawn: No amber object is blue.Report {K}#a dawn: Every amber object is not blue.True {K}#a.True {K}#a.World dawn: Object Ada is amber.','World dawn: Object Ada is not blue.','supported','Only the declared negative-rule alias normalizes to identical reference payload.',{'references.0.report_ordinals':[1,2],'references.0.true_ordinals':[3,4],'diagnostics.inventory.0.admissions':[['bridge',3,K+'#a'],['bridge',4,K+'#a'],['world',5]],'counts.statements':5})
for name,p in [('frame',f'Report {K}#a dawn: Object Ada is amber.Report {K}#a dusk: Object Ada is amber.'),('reversed_exclusion',f'Report {K}#a dawn: No amber object is blue.Report {K}#a dawn: No blue object is amber.'),('polarity',f'Report {K}#a dawn: Object Ada is amber.Report {K}#a dawn: Object Ada is not amber.')]:
 add('reference_conflict_'+name,p,'World dawn: Object Bea is coral.','abstain','Unselected conflicting reference payload invalidates the case before relevance.',reason='conflicting_report_reference',details={'references':[K+'#a']})
add('reference_dangling',f'True {O}#z.True {K}#a.','World dawn: Object Ada is amber.','abstain','All unresolved truth references are listed in ASCII order.',reason='unresolved_truth_reference',details={'references':sorted([O+'#z',K+'#a'])})
add('reference_conflict_before_dangling',f'Report {K}#a dawn: Object Ada is amber.Report {K}#a dawn: Object Ada is blue.True {O}#z.','World dawn: Object Ada is amber.','abstain','Payload conflict precedes unresolved truth even when both are present.',reason='conflicting_report_reference',details={'references':[K+'#a']})
# Grammar cases are envelope-valid, so abstention rather than request failure is expected.
good='World dawn: Object Ada is amber.'
for name,claim in [('preperiod','World dawn: Object Ada is amber .'),('tablike_unicode','World dawn: Object Ada is\u00a0amber.'),('no_period',good[:-1]),('double_period',good+'.'),('rule','World dawn: Every amber object is blue.'),('bare','Object Ada is amber.'),('double_claim',good+good),('duplicate_keys',f'Account [{K},{K}] dawn: Object Ada is amber.'),('five_keys','Account [a/v/e,b/v/e,c/v/e,d/v/e,f/v/e] dawn: Object Ada is amber.'),('reserved_property','World dawn: Object Ada is object.'),('uppercase_property','World dawn: Object Ada is Amber.'),('long_entity','World dawn: Object '+('A'+'a'*32)+' is amber.')]:
 add('grammar_claim_'+name,'Malformed premise.',claim,'abstain','Claim grammar failure takes precedence over the deliberately malformed passage.',reason='unsupported_claim_grammar')
for name,p,index in [('preperiod',good[:-1]+' .',1),('double_period',good+'.',2),('tail',good+'World dawn: Object Ada is blue',2),('early_before_tail','Broken.'+good[:-1],1),('claim_in_passage','Asserts '+K+' dawn: Object Ada is amber.',1),('unicode_space','\u00a0'+good,1),('empty_segment','.'+good,1),('no_period',good[:-1],1)]:
 add('grammar_passage_'+name,p,good,'abstain','Deterministic period-inclusive scan reports the first bad statement, without repairing whitespace or tails.',reason='unsupported_passage_grammar',details={'passage_index':1,'passage_id':'p1','statement_index':index})
add('grammar_uncited_passage',[good,'Broken.'],good,'abstain','An uncited second passage still must parse.',reason='unsupported_passage_grammar',details={'passage_index':2,'passage_id':'p2','statement_index':1})
add('grammar_zero_separator','  '+good+good+'   ','  '+good+'  ','supported','Only outer ASCII spaces are insignificant; zero interstatement spaces are allowed.',{'counts.statements':2,'records.0.text':good[:-1]})
# Limits and ordered failures.
add('bound_64_statements',good*64,good,'supported','Raw duplicate statements count, but exactly 64 is admissible.',{'counts.statements':64})
add('bound_65_statements',good*65,good,'abstain','Deduplication cannot hide the 65th raw premise.',reason='statement_limit',details={'statement_count':65,'maximum':64})
add('grammar_before_limit',good*65+'Broken.',good,'abstain','Passage parsing precedes statement counting even after an over-limit parsed prefix.',reason='unsupported_passage_grammar',details={'passage_index':1,'passage_id':'p1','statement_index':66})
entities=['Ada','Bea','Cia','Dae','Ena','Fae','Gia','Hae','Ira']
for n in (8,9):
 p=''.join(f'World dawn: Object {e} is amber.' for e in entities[:n])
 add('bound_entities_'+str(n),p,good,'supported' if n==8 else 'abstain','Entity inventory includes all supplied scopes.',{'counts.entities':8} if n==8 else None,reason=None if n==8 else 'symbol_limit',details=None if n==8 else {'counts':{'entities':9,'properties':1,'frames':1,'source_keys':0},'exceeded':['entities']})
props=['amber','blue','coral','dun','ecru','fawn','gold','hazel','indigo','jade','khaki']
for n in (10,11):
 p=''.join(f'World dawn: Object Ada is {q}.' for q in props[:n])
 add('bound_properties_'+str(n),p,good,'supported' if n==10 else 'abstain','Property limit counts every distinct body property.',{'counts.properties':10} if n==10 else None,reason=None if n==10 else 'symbol_limit',details=None if n==10 else {'counts':{'entities':1,'properties':11,'frames':1,'source_keys':0},'exceeded':['properties']})
for n in (4,5):
 p=''.join(f'World f{i}: Object Ada is amber.' for i in range(n))
 add('bound_frames_'+str(n),p,'World f0: Object Ada is amber.','supported' if n==4 else 'abstain','Frame inventory does not merge distinct frame identifiers.',{'counts.frames':4} if n==4 else None,reason=None if n==4 else 'symbol_limit',details=None if n==4 else {'counts':{'entities':1,'properties':1,'frames':5,'source_keys':0},'exceeded':['frames']})
for n in (4,5):
 p=''.join(f'Complete s/v/e{i}.' for i in range(n))
 add('bound_keys_'+str(n),p,good,'not_established' if n==4 else 'abstain','Complete-only source keys count although they create no additional diagnostic frame.',{'counts.source_keys':4} if n==4 else None,reason=None if n==4 else 'symbol_limit',details=None if n==4 else {'counts':{'entities':1,'properties':1,'frames':1,'source_keys':5},'exceeded':['source_keys']})
for n in (32,33):
 p=''.join(f'Report {K}#e{i} dawn: Object Ada is amber.' for i in range(n))
 add('bound_references_'+str(n),p,f'Account [{K}] dawn: Object Ada is amber.','supported' if n==32 else 'abstain','References count distinct full key-entry identifiers rather than deduplicated bodies.',{'counts.references':32} if n==32 else None,reason=None if n==32 else 'reference_limit',details=None if n==32 else {'reference_count':33,'maximum':32})
add('bound_query_only_entity',''.join(f'World dawn: Object {e} is amber.' for e in entities[:8]),'World dawn: Object Ira is amber.','abstain','The ninth entity occurs only in the query but still exceeds the symbol bound.',reason='symbol_limit',details={'counts':{'entities':9,'properties':1,'frames':1,'source_keys':0},'exceeded':['entities']})
# Exact diagnostic shape for a closed empty account, and disconnected/other-object inconsistency.
add('diagnostic_empty_complete',f'Complete {K}.','Asserts '+K+' noon: Object Ada is amber.','contradicted','Complete-only key produces just the query world and selected account descriptors, each with an isolated query predicate.',{'diagnostics':{'entity_universe':['Ada'],'query_predicate':'amber','scan_complete':True,'inventory':[{'scope':['world','noon'],'admissions':[],'components':[{'predicates':['amber'],'inconsistent_entities':[]}],'consistent':True},{'scope':['account',[K],'noon'],'admissions':[],'components':[{'predicates':['amber'],'inconsistent_entities':[]}],'consistent':True}]}})
add('diagnostic_other_entity_disconnected','World dawn: Object Bea is blue.World dawn: Object Bea is not blue.World dawn: Object Ada is amber.','World dawn: Object Ada is amber.','supported','Inventory must record Bea\'s disconnected conflict while preserving Ada\'s supported local answer.',{'diagnostics.entity_universe':['Ada','Bea'],'diagnostics.inventory.0.components':[{'predicates':['amber'],'inconsistent_entities':[]},{'predicates':['blue'],'inconsistent_entities':['Bea']}],'diagnostics.inventory.0.consistent':False,'evaluation.true_witness':[True]})
add('diagnostic_query_only_grounding','World dawn: Every amber object is not amber.World dusk: Object Bea is blue.','World dawn: Object Ada is not amber.','supported','A rule applies to a query-only object; diagnostics include every case entity, including other-frame objects.',{'diagnostics.entity_universe':['Ada','Bea'],'evaluation.true_witness':[False],'evaluation.false_witness':None})
assert len(C)==len({x['case']['id'] for x in C})
rows=[]
for r in C:
    checks=dict(r['expected'].pop('checks'))
    checks['details']=r['expected'].pop('details')
    r['expected']['checks']=[{'path':[int(v) if v.isdigit() else v for v in k.split('.')],'value':v} for k,v in checks.items()]
    rows.append({'input':r['case'],'expected':r['expected'],'rationale':r['rationale'],'family':r['case']['id'].split('_')[0]})
(D/'challenge.json').write_bytes(canon({'protocol':1,'scope':'Independent synthetic contract-only bounded scoped-unary challenge; not a full oracle or representative corpus','authoring_basis':'SCOPED_SUPPORT_CONTRACT.md only; no candidate or existing tests inspected','cases':rows})+b'\n')
dataset_hash=hashlib.sha256((D/'challenge.json').read_bytes()).hexdigest()
for old in D.glob('batch_*.json'): old.unlink()
for i in range(0,len(rows),16):
    env={'protocol':1,'dataset_sha256':dataset_hash,'cases':[r['input'] for r in rows[i:i+16]]}
    env['input_sha256']=hashlib.sha256(canon(env)).hexdigest()
    (D/f'batch_{i//16+1:02}.json').write_bytes(canon(env)+b'\n')
print(len(rows),'cases')
