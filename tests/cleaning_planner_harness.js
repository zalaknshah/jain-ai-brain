'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=path.join(__dirname,'..'), html=fs.readFileSync(path.join(root,'web/cleaning.html'),'utf8');
class Element {
  constructor(id){Object.assign(this,{id,value:'',textContent:'',checked:false,hidden:false,disabled:false,children:[]});}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];this.textContent='';}
}
const elements={},events={},calls=[];
for(const match of html.matchAll(/id="([^"]+)"/g)){assert.ok(!elements[match[1]]);elements[match[1]]=new Element(match[1]);}
const scenario=process.argv[2],actual=scenario.startsWith('real_');
const token='test-alice-'+'a'.repeat(32);
elements.user.value='alice';elements.scope.value='home';elements.token.value=token;
elements.api.value=actual?process.env.JACE_TEST_API:'http://127.0.0.1:8787';
if(actual){const u=new URL(elements.api.value);assert.equal(u.hostname,'127.0.0.1');assert.equal(u.protocol,'http:');}
const baseProfile={surface:'wooden_furniture',water_policy:'avoid',time_budget_minutes:10,supplies_policy:'existing_only'};
let memory={memory_id:7,user_id:'alice',memory_scope:'home',source:'cleaning_profile_v1',content:JSON.stringify({version:1,profile:baseProfile}),revision:'a'.repeat(64),expires_at:null};
let responder=null;
const response=(data,status=200,declared=null)=>{
 const bytes=new TextEncoder().encode(JSON.stringify(data));let sent=false;
 return{ok:status>=200&&status<300,status,headers:{get:()=>declared===null?String(bytes.length):declared},body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:async()=>{},releaseLock:()=>{}})}};
};
const planData=()=>({user_id:'alice',memory_scope:'home',status:'planned',action:null,actions_executed:false,profile_memory:{...memory},profile_applied:JSON.parse(memory.content).profile,context_at:'2026-11-04T12:00:00Z',steps:[{id:'inspect',instruction:'Inspect; no actions performed.'}],grounding:'Unverified sample summaries, not Agama quotations.',limits:['Authored conditional checklist.']});
const preview=()=>({memory:{...memory},unattributed_audit_entries:0,requires_delete_confirmation:true,requires_unattributed_audit_cleanup_confirmation:false});
async function normal(url,options){
 const u=new URL(url),method=options.method||'GET';
 if(u.pathname==='/health')return response({cleaning_planner_protocol:1,memory_management_protocol:1});
 if(u.pathname==='/v1/memory/alice')return response({memory_scope:'home',memories:[{...memory}],next_before_id:null});
 if(u.pathname==='/v1/memory-item/7')return response(preview());
 const body=JSON.parse(options.body);assert.equal(body.user_id,'alice');
 if(u.pathname==='/v1/cleaning-profiles'){
  assert.equal(body.confirm_save,true);
  if(method==='PATCH')assert.equal(body.expected_revision,memory.revision);
  else{assert.equal(method,'POST');assert.equal(body.memory_scope,'home');}
  memory.content=JSON.stringify({version:1,profile:body.profile});memory.revision='b'.repeat(64);if(method==='POST')memory.expires_at=body.expires_at;
  return response({memory:{...memory}},method==='POST'?201:200);
 }
 if(u.pathname==='/v1/plans/cleaning'){
  assert.equal(body.profile_memory_id,memory.memory_id);assert.equal(body.expected_profile_revision,memory.revision);return response(planData());
 }
 throw new Error('Unexpected route '+method+' '+u.pathname);
}
const sandbox={document:{querySelector:q=>{assert.ok(elements[q.slice(1)],q);return elements[q.slice(1)];},createElement:t=>new Element(t)},window:{addEventListener:(name,fn)=>events[name]=fn},URL,TextEncoder,TextDecoder,Uint8Array,AbortController,
 fetch:async(url,options)=>{calls.push({url,options});return actual?fetch(url,options):(responder?responder(url,options):normal(url,options));}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'web/cleaning-planner.js'),'utf8'),sandbox);
const click=async id=>elements[id].onclick();
const tick=async()=>{for(let n=0;n<15;n++)await Promise.resolve();};
const deferred=()=>{let resolve;return{promise:new Promise(r=>resolve=r),get resolve(){return resolve;}};};
const writeCalls=()=>calls.filter(c=>c.url.endsWith('/v1/cleaning-profiles')&&['POST','PATCH'].includes(c.options.method));
const planCalls=()=>calls.filter(c=>c.url.endsWith('/v1/plans/cleaning'));
const open=async()=>{await click('load');assert.ok(elements.profiles.children.length);await elements.profiles.children[0].children[1].onclick();};
const fill=()=>{for(const [id,value] of Object.entries({surface:'wooden_furniture',water:'avoid',minutes:'10',supplies:'existing_only'})){elements[id].value=value;elements[id].oninput();}};
async function actualChange(path,method,body){const r=await fetch(elements.api.value+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)});assert.equal(r.status,200);return r.json();}
(async()=>{
 assert.equal(calls.length,0);assert.equal(elements.confirm.checked,false);assert.equal(elements.plan.disabled,true);
 if(scenario==='create_review_plan'){
  fill();await click('save');assert.equal(calls.length,0);
  elements.confirm.checked=true;const pending=click('save');assert.equal(elements.confirm.checked,false);await click('save');await pending;
  assert.equal(writeCalls().length,1);assert.equal(planCalls().length,0);assert.equal(elements.plan.disabled,false);
  await click('plan');assert.equal(planCalls().length,1);assert.equal(elements.result.hidden,false);assert.match(elements.grounding.textContent,/Unverified/);
  assert.equal(elements.steps.children.length,1);assert.equal(elements.confirm.checked,false);
  for(const c of calls){assert.equal(c.options.redirect,'error');assert.equal(c.options.credentials,'omit');assert.equal(c.options.cache,'no-store');if(c.url.endsWith('/health'))assert.ok(!c.options.headers.Authorization);}
 } else if(scenario==='edit_and_consumed_consent'){
  await open();elements.confirm.checked=true;elements.minutes.value='15';elements.minutes.oninput();assert.equal(elements.confirm.checked,false);assert.equal(elements.plan.disabled,true);
  await click('plan');assert.equal(planCalls().length,0);await click('save');assert.equal(writeCalls().length,0);
  elements.confirm.checked=true;await click('save');assert.equal(writeCalls().length,1);assert.equal(writeCalls()[0].options.method,'PATCH');
  assert.equal(JSON.parse(writeCalls()[0].options.body).expected_revision,'a'.repeat(64));assert.equal(elements.expires.disabled,true);
  await click('plan');assert.match(elements['plan-info'].textContent,/15 minutes/);await click('new');assert.equal(elements.surface.value,'');assert.equal(elements.plan.disabled,true);
 } else if(scenario==='explicit_paging_selection'){
  responder=(u,o)=>u.includes('/v1/memory/alice')?response({memory_scope:'home',memories:[{...memory,memory_id:u.includes('before_id')?3:7}],next_before_id:u.includes('before_id')?null:7}):normal(u,o);
  await click('load');assert.equal(elements.plan.disabled,true);assert.equal(planCalls().length,0);assert.equal(elements.older.disabled,false);
  await click('older');assert.equal(elements.profiles.children.length,1);assert.ok(calls.some(c=>c.url.includes('before_id=7')));assert.equal(elements.older.disabled,true);
 } else if(scenario==='stale_health_boundary'){
  const hold=deferred();responder=()=>hold.promise;fill();elements.confirm.checked=true;const p=click('save');await tick();
  elements.api.value='https://other.example';elements.api.oninput();hold.resolve(response({cleaning_planner_protocol:1,memory_management_protocol:1}));await p;
  assert.equal(calls.length,1);assert.equal(elements.token.value,'');assert.equal(elements.surface.value,'');assert.equal(elements.confirm.checked,false);assert.equal(writeCalls().length,0);
 } else if(scenario==='stale_body_boundary'){
  const hold=deferred();responder=(u,o)=>u.includes('/v1/memory/alice')?Promise.resolve({ok:true,headers:{get:()=>null},body:{getReader:()=>({read:()=>hold.promise,cancel:async()=>{},releaseLock:()=>{}})}}):normal(u,o);
  const p=click('load');await tick();elements.user.value='bob';elements.user.oninput();hold.resolve({done:true});await p;
  assert.equal(elements.profiles.children.length,0);assert.equal(elements.token.value,'');assert.equal(elements.result.hidden,true);
 } else if(scenario==='uncertain_write_no_retry'){
  fill();const hold=deferred();responder=(u,o)=>u.endsWith('/v1/cleaning-profiles')?hold.promise:normal(u,o);
  elements.confirm.checked=true;const p=click('save');await tick();assert.equal(writeCalls().length,1);await click('cancel');assert.match(elements.status.textContent,/may have completed/);
  hold.resolve(response({memory}));await p;assert.equal(writeCalls().length,1);assert.equal(elements.surface.value,'');assert.equal(elements.plan.disabled,true);assert.match(elements.status.textContent,/may have completed/);
 } else if(scenario==='plan_conflict_no_retry'){
  await open();responder=(u,o)=>u.endsWith('/v1/plans/cleaning')?response({},409):normal(u,o);
  await click('plan');await click('plan');assert.equal(planCalls().length,1);assert.equal(elements.result.hidden,true);assert.equal(elements.plan.disabled,true);assert.match(elements.status.textContent,/Reload/);
 } else if(scenario==='invalid_inputs_and_protocol'){
  fill();for(const value of ['0','1.5','1e1',' 10','121','10\n']){elements.minutes.value=value;elements.confirm.checked=true;await click('save');assert.equal(calls.length,0);}
  fill();for(const value of ['home\n','Home',' home']){elements.scope.value=value;elements.confirm.checked=true;await click('save');assert.equal(calls.length,0);}
  elements.scope.value='home';for(const value of ['http://example.com','https://user:pass@example.com','https://exa\nmple.com','https://example.com/path']){elements.api.value=value;await click('load');assert.equal(calls.length,0);}
  elements.api.value='http://127.0.0.1:8787';responder=()=>response({memory_management_protocol:1});await click('load');assert.equal(calls.length,1);assert.match(elements.status.textContent,/protocol/);
 } else if(scenario==='wrong_scope_and_actions'){
  memory.memory_scope='work';await click('load');assert.equal(elements.profiles.children.length,0);memory.memory_scope='home';await open();
  responder=(u,o)=>u.endsWith('/v1/plans/cleaning')?response({...planData(),actions_executed:true}):normal(u,o);await click('plan');assert.equal(elements.result.hidden,true);
  responder=null;await open();responder=(u,o)=>u.endsWith('/v1/plans/cleaning')?response({...planData(),profile_memory:{...memory,revision:'f'.repeat(64)}}):normal(u,o);await click('plan');assert.equal(elements.result.hidden,true);
 } else if(scenario==='text_render_and_privacy_reset'){
  await open();responder=(u,o)=>u.endsWith('/v1/plans/cleaning')?response({...planData(),steps:[{instruction:'<img src=x onerror=alert(1)>'}],grounding:'<script>private</script>'}):normal(u,o);
  await click('plan');assert.equal(elements.steps.children[0].textContent,'<img src=x onerror=alert(1)>');assert.equal(elements.steps.children[0].children.length,0);
  elements.scope.value='work';elements.scope.oninput();assert.equal(elements.token.value,token);assert.equal(elements.surface.value,'');assert.equal(elements.grounding.textContent,'');assert.equal(elements.result.hidden,true);
  fill();elements.confirm.checked=true;events.pagehide();assert.equal(elements.token.value,'');assert.equal(elements.confirm.checked,false);assert.equal(elements.minutes.value,'');
 } else if(scenario==='oversized_response'){
  responder=(u,o)=>u.endsWith('/health')?normal(u,o):response({text:'x'.repeat(1024*1024+1)},200,'1');await click('load');assert.match(elements.status.textContent,/limit/);assert.equal(elements.profiles.children.length,0);
 } else if(scenario==='stale_plan_after_cancel'){
  await open();const hold=deferred();responder=(u,o)=>u.endsWith('/v1/plans/cleaning')?hold.promise:normal(u,o);const p=click('plan');await tick();await click('cancel');hold.resolve(response(planData()));await p;assert.equal(elements.result.hidden,true);assert.equal(elements.steps.children.length,0);
 } else if(scenario==='save_expiry_binding'){
  for(const [requested,returned] of [['2027-01-01T00:00:00Z',null],['','2027-01-01T00:00:00Z'],['2027-01-01T00:00:00.000001Z','2027-01-01T00:00:00.000002+00:00']]){
   await click('new');fill();elements.expires.value=requested;
   responder=async(u,o)=>{const result=await normal(u,o);return u.endsWith('/v1/cleaning-profiles')?response({memory:{...memory,expires_at:returned}}):result;};
   elements.confirm.checked=true;await click('save');assert.equal(elements.plan.disabled,true);assert.match(elements.status.textContent,/may have completed/);
  }
  await click('new');fill();elements.expires.value='2027-01-01T01:00:00.123456+01:00';
  responder=async(u,o)=>{const result=await normal(u,o);return u.endsWith('/v1/cleaning-profiles')?response({memory:{...memory,expires_at:'2027-01-01T00:00:00.123456+00:00'}}):result;};
  elements.confirm.checked=true;await click('save');assert.equal(elements.plan.disabled,false);assert.match(elements.status.textContent,/confirmed/);
 } else if(scenario==='invalid_expiry_before_network'){
  for(const expires of ['2027-02-30T00:00:00Z','2027-01-01T00:00:00-00:00','2027-01-01T00:00:00Z\n','0001-01-01T00:00:00+01:00','9999-12-31T23:59:59-01:00','2027-01-01T00:00:00.1234567Z']){
   await click('new');fill();elements.expires.value=expires;elements.confirm.checked=true;await click('save');assert.equal(calls.length,0);assert.equal(elements.confirm.checked,false);
  }
 } else if(scenario==='update_expiry_binding'){
  memory.expires_at='2027-01-01T00:00:00.000001+00:00';await open();
  responder=async(u,o)=>{const result=await normal(u,o);return u.endsWith('/v1/cleaning-profiles')?response({memory:{...memory,expires_at:null}}):result;};
  elements.confirm.checked=true;await click('save');assert.equal(elements.plan.disabled,true);assert.match(elements.status.textContent,/may have completed/);
 } else if(scenario==='real_create_edit_plan'){
  fill();await click('save');assert.equal(writeCalls().length,0);elements.confirm.checked=true;await click('save');assert.match(elements.status.textContent,/confirmed/);assert.equal(planCalls().length,0);
  await click('plan');assert.equal(elements.result.hidden,false);assert.equal(elements.steps.children.length,6);assert.match(elements.steps.children.map(x=>x.textContent).join('\n'),/water and liquid cleaning products out/);
  await open();elements.water.value='follow_surface_guidance';elements.water.oninput();elements.minutes.value='20';elements.minutes.oninput();elements.confirm.checked=true;await click('save');assert.match(elements.status.textContent,/confirmed/);
  await click('plan');assert.equal(elements.result.hidden,false);assert.match(elements['plan-info'].textContent,/20 minutes/);assert.match(elements.grounding.textContent,/unverified sample/);
 } else if(scenario==='real_conflict'){
  await open();const selected=vm.runInContext('selected',sandbox);
  await actualChange('/v1/cleaning-profiles','PATCH',{memory_id:selected.memory.memory_id,profile:{...baseProfile,time_budget_minutes:30},expected_revision:selected.memory.revision,confirm_save:true});
  await click('plan');assert.equal(elements.result.hidden,true);assert.match(elements.status.textContent,/Reload/);assert.equal(planCalls().length,1);
  await open();const latest=vm.runInContext('selected',sandbox);await actualChange('/v1/cleaning-profiles','PATCH',{memory_id:latest.memory.memory_id,profile:{...baseProfile,time_budget_minutes:40},expected_revision:latest.memory.revision,confirm_save:true});
  elements.minutes.value='50';elements.minutes.oninput();elements.confirm.checked=true;await click('save');assert.match(elements.status.textContent,/Reload/);assert.equal(writeCalls().length,1);
 } else if(scenario==='real_expiry_and_isolation'){
  await open();const selected=vm.runInContext('selected',sandbox);await actualChange('/v1/memory-expiration','PATCH',{memory_id:selected.memory.memory_id,expires_at:'2000-01-01T00:00:00Z'});
  await click('plan');assert.match(elements.status.textContent,/404/);assert.equal(elements.result.hidden,true);
  elements.token.value='test-bob-'+'b'.repeat(32);elements.token.oninput();fill();elements.confirm.checked=true;await click('save');assert.match(elements.status.textContent,/403/);
 } else throw new Error('Unknown scenario '+scenario);
 console.log('PASS '+scenario);
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
