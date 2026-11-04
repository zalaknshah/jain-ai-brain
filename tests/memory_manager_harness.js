'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const path = require('path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'web/memory.html'), 'utf8');
class Element {
  constructor(id) { this.id=id;this.value='';this.textContent='';this.checked=false;this.hidden=false;this.disabled=false;this.children=[]; }
  append(...values) { this.children.push(...values); }
  replaceChildren(...values) { this.children=[...values];this.textContent=''; }
}
const elements={};
for (const match of html.matchAll(/id="([^"]+)"/g)) elements[match[1]]=new Element(match[1]);
const events={},calls=[];
const scenario=process.argv[2];
const actual=scenario.startsWith('real_');
const token=actual?'test-alice-'+ 'a'.repeat(32):'synthetic-'+ 'a'.repeat(32);
Object.assign(elements.user,{value:'alice'});Object.assign(elements.scope,{value:'home'});
Object.assign(elements.api,{value:actual?process.env.JACE_TEST_API:'http://127.0.0.1:8787'});Object.assign(elements.token,{value:token});
if(actual && (new URL(elements.api.value).hostname!=='127.0.0.1'||new URL(elements.api.value).protocol!=='http:')) throw new Error('Real fixture requires literal loopback HTTP');
let memory={memory_id:7,user_id:'alice',memory_scope:'home',content:'I prefer quiet rooms',revision:'a'.repeat(64),expires_at:null};
let auditCount=0, responder=null;
const response=(data,status=200,declared=null)=>{
  const bytes=new TextEncoder().encode(JSON.stringify(data));let sent=false;
  return {ok:status>=200&&status<300,status,headers:{get:()=>declared===null?String(bytes.length):declared},
    body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:async()=>{},releaseLock:()=>{}})}};
};
const preview=()=>({memory:{...memory},unattributed_audit_entries:auditCount,requires_delete_confirmation:true,requires_unattributed_audit_cleanup_confirmation:auditCount>0});
async function defaultResponder(url,options) {
  const u=new URL(url),method=options.method||'GET';
  if (u.pathname==='/health') return response({memory_management_protocol:1});
  if (method==='GET'&&u.pathname==='/v1/memory/alice') return response({memory_scope:'home',memories:[{...memory}],next_before_id:null});
  if (method==='GET'&&u.pathname==='/v1/memory-item/7') return response(preview());
  if (method==='PATCH') {
    const body=JSON.parse(options.body);
    assert.equal(body.expected_revision,memory.revision);
    if ('content' in body) memory.content=body.content;
    if ('expires_at' in body) memory.expires_at=body.expires_at;
    memory.revision=memory.revision[0]==='a'?'b'.repeat(64):'c'.repeat(64);
    return response({memory:{...memory},accepted:true});
  }
  if (method==='DELETE')return response({deleted:1,memory_id:7,user_id:'alice'});
  throw new Error('Unexpected mock route '+method+' '+u.pathname);
}
const sandbox={document:{querySelector:q=>elements[q.slice(1)],createElement:tag=>new Element(tag)},
  window:{addEventListener:(name,fn)=>events[name]=fn},URL,TextDecoder,TextEncoder,Uint8Array,AbortController,
  fetch:async(url,options)=>{calls.push({url,options});return actual?fetch(url,options):(responder?responder(url,options):defaultResponder(url,options));}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'web/memory-manager.js'),'utf8'),sandbox);
const click=async id=>elements[id].onclick();
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const open=async()=>{await click('load');await elements.memories.children[0].children[2].onclick();};
const writes=()=>calls.filter(c=>['PATCH','DELETE'].includes(c.options.method));
(async()=>{
  assert.equal(calls.length,0,'no automatic network');
  if(scenario==='real_lifecycle') {
    await open();assert.equal(elements.content.value,'Original home fixture');
    elements.content.value='Reviewed from actual Node HTTP client';await click('save');assert.match(elements.status.textContent,/confirmed/);
    await open();assert.equal(elements.content.value,'Reviewed from actual Node HTTP client');
    elements.expires.value='2000-01-01T00:00:00Z';await click('set-expiry');await open();
    assert.match(elements['expiry-info'].textContent,/2000-01-01/);assert.match(elements['delete-warning'].textContent,/ALL 2/);
    await click('delete');assert.equal(writes().filter(c=>c.options.method==='DELETE').length,0);
    elements['confirm-delete'].checked=true;elements['confirm-audit'].checked=true;await click('delete');
    assert.match(elements.status.textContent,/confirmed deletion/);assert.equal(writes().filter(c=>c.options.method==='DELETE').length,1);
  } else if(scenario==='real_conflict') {
    await open();const selected=vm.runInContext('selected.memory',sandbox);
    const changed=await fetch(elements.api.value+'/v1/memory',{method:'PATCH',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({memory_id:selected.memory_id,content:'Another client changed this memory'})});
    assert.equal(changed.status,200);await changed.json();elements.content.value='Stale browser draft';await click('save');
    assert.match(elements.status.textContent,/Reload/);assert.equal(elements.editor.hidden,true);assert.equal(writes().length,1);
  } else if(scenario==='real_owner_isolation') {
    elements.token.value='test-bob-'+ 'b'.repeat(32);await click('load');assert.match(elements.status.textContent,/403/);
    assert.equal(elements.memories.children.length,0);assert.equal(writes().length,0);
  } else if(scenario==='review_correct') {
    await open();assert.equal(elements.content.value,memory.content);assert.equal(elements.editor.hidden,false);
    elements.content.value='Reviewed correction';elements.content.oninput();await click('save');
    assert.equal(memory.content,'Reviewed correction');assert.equal(writes().length,1);
    assert.equal(elements.editor.hidden,true);assert.match(elements.status.textContent,/confirmed/);
    for(const call of calls){assert.equal(call.options.redirect,'error');assert.equal(call.options.credentials,'omit');assert.equal(call.options.cache,'no-store');}
    assert.ok(!calls[0].options.headers.Authorization);assert.equal(writes()[0].options.headers.Authorization,'Bearer '+token);
  } else if(scenario==='typed_profile'||scenario==='typed_inventory') {
    memory.source=scenario==='typed_inventory'?'wardrobe_inventory_v1':'cleaning_profile_v1';await open();assert.equal(elements.save.disabled,true);assert.equal(elements.content.disabled,true);
    assert.match(elements['record-info'].textContent,/Typed profile or inventory/);await click('save');assert.equal(writes().length,0);
    assert.equal(elements['set-expiry'].disabled,false);elements.expires.value='2000-01-01T00:00:00Z';await click('set-expiry');assert.equal(writes().length,1);
  } else if(scenario==='expiry') {
    await open();elements.expires.value='2027-01-01T00:00:00Z';await click('set-expiry');assert.equal(memory.expires_at,'2027-01-01T00:00:00Z');
    await open();await click('clear-expiry');assert.equal(memory.expires_at,null);assert.equal(writes().length,2);
  } else if(scenario==='delete_choices') {
    auditCount=3;await open();assert.equal(elements['confirm-delete'].checked,false);assert.equal(elements['confirm-audit'].checked,false);
    assert.match(elements['delete-warning'].textContent,/ALL 3.*ALL memory scopes/);
    await click('delete');assert.equal(writes().length,0);elements['confirm-delete'].checked=true;
    await click('delete');assert.equal(writes().length,0);elements['confirm-audit'].checked=true;
    const promise=click('delete');assert.equal(elements['confirm-delete'].checked,false);assert.equal(elements['confirm-audit'].checked,false);
    await click('delete');await promise;assert.equal(writes().length,1);
    assert.equal(writes()[0].options.headers['X-JACE-Confirm-Audit-Cleanup'],'all-unattributed-for-owner');
    assert.equal(writes()[0].options.headers['X-JACE-If-Memory-Revision'],'a'.repeat(64));
  } else if(scenario==='stale_identity') {
    const hold=deferred();responder=(u,o)=>u.includes('/v1/memory/alice')?hold.promise:defaultResponder(u,o);
    const pending=click('load');await tick();elements.user.value='bob';elements.user.oninput();
    assert.equal(elements.token.value,'');hold.resolve(response({memory_scope:'home',memories:[memory],next_before_id:null}));await pending;
    assert.equal(elements.memories.children.length,0);assert.equal(elements.editor.hidden,true);assert.equal(elements['stored-content'].textContent,'');
  } else if(scenario==='changed_during_health') {
    const hold=deferred();responder=()=>hold.promise;const pending=click('load');await tick();
    elements.api.value='https://different.example';elements.api.oninput();hold.resolve(response({memory_management_protocol:1}));await pending;
    assert.equal(calls.length,1);assert.equal(elements.token.value,'');assert.ok(!calls[0].options.headers.Authorization);
  } else if(scenario==='cancel_uncertain_write') {
    await open();const hold=deferred();responder=(u,o)=>o.method==='PATCH'?hold.promise:defaultResponder(u,o);
    elements.content.value='Reviewed change';const pending=click('save');await tick();assert.equal(writes().length,1);
    await click('cancel');assert.match(elements.status.textContent,/may have completed/);hold.resolve(response({memory}));await pending;
    assert.equal(elements.editor.hidden,true);assert.equal(writes().length,1);assert.match(elements.status.textContent,/may have completed/);
  } else if(scenario==='conflict_no_retry') {
    await open();responder=(u,o)=>o.method==='PATCH'?response({error:'Conflict'},409):defaultResponder(u,o);
    elements.content.value='Change';await click('save');await click('save');assert.equal(writes().length,1);
    assert.equal(elements.editor.hidden,true);assert.match(elements.status.textContent,/Reload/);
  } else if(scenario==='pagination') {
    responder=(u,o)=>u.includes('/v1/memory/alice')?response({memory_scope:'home',memories:[{...memory,memory_id:u.includes('before_id')?3:5}],next_before_id:u.includes('before_id')?null:5}):defaultResponder(u,o);
    await click('load');assert.equal(elements.older.disabled,false);await click('older');assert.equal(elements.memories.children.length,1);
    assert.ok(calls.some(c=>c.url.includes('before_id=5')));assert.equal(elements.older.disabled,true);
  } else if(scenario==='wrong_scope_and_xss') {
    memory.content='<img src=x onerror=alert(1)>';await open();assert.equal(elements['stored-content'].textContent,memory.content);
    assert.equal(elements['stored-content'].children.length,0);
    memory.memory_scope='work';await click('load');assert.equal(elements.memories.children.length,0);assert.equal(elements.editor.hidden,true);
  } else if(scenario==='validation_and_protocol') {
    for(const url of ['http://example.com','https://user:pass@example.com','https://example.com/path','https://example.com/?x=1']) {
      elements.api.value=url;await click('load');assert.equal(calls.length,0);
    }
    elements.api.value='http://127.0.0.1:8787';elements.scope.value='home\n';await click('load');assert.equal(calls.length,0);
    elements.scope.value='home';responder=()=>response({memory_scope_protocol:1});await click('load');assert.equal(calls.length,1);assert.match(elements.status.textContent,/protocol/);
  } else if(scenario==='pagehide_and_draft') {
    await open();elements.content.value='Unsaved private text';elements['confirm-delete'].checked=true;elements.content.oninput();
    assert.equal(elements['confirm-delete'].checked,false);assert.equal(elements['stored-content'].textContent,'I prefer quiet rooms');
    events.pagehide();assert.equal(elements.content.value,'');assert.equal(elements.token.value,'');assert.equal(elements['stored-content'].textContent,'');
  } else if(scenario==='oversized_response') {
    responder=(u,o)=>u.endsWith('/health')?defaultResponder(u,o):response({text:'x'.repeat(1024*1024+1)},200,'1');
    await click('load');assert.match(elements.status.textContent,/limit/);assert.equal(elements.memories.children.length,0);
  } else throw new Error('Unknown scenario '+scenario);
  console.log('PASS '+scenario);
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
