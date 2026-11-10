'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert'), path = require('path');
const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'web/context.html'), 'utf8');
class Element {
  constructor(id) { Object.assign(this, {id, value:'', textContent:'', checked:false, hidden:false, disabled:false, children:[]}); }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = [...items]; this.textContent = ''; }
  set innerHTML(_) { throw new Error('Unsafe HTML rendering'); }
}
const elements = {}, events = {}, calls = [];
for (const match of html.matchAll(/id="([^"]+)"/g)) { assert.ok(!elements[match[1]]); elements[match[1]] = new Element(match[1]); }
elements.review.hidden = true; elements.result.hidden = true;
const token = 'test-alice-' + 'a'.repeat(32), question = 'How can I clean gently?';
const scenario = process.argv[2], actual = scenario.startsWith('real_');
elements.user.value = 'alice'; elements.scope.value = 'home'; elements.token.value = token;
elements.api.value = actual ? process.env.JACE_TEST_API : 'http://127.0.0.1:8787'; elements.question.value = question;
if (actual) { const u = new URL(elements.api.value); assert.equal(u.hostname, '127.0.0.1'); assert.equal(u.protocol, 'http:'); }
const now = '2026-11-04T12:00:00+00:00';
const source = {entry_id:'gentle',title:'Gentle care',principle:'Avoid harm.\nFull principle.',guidance:'Review before acting.',source:'Sample, not an exact quote',work:null,language:'en',edition:null,location:null,license:null,verified:false,tags:['clean','gentle']};
const memory = {memory_id:7,user_id:'alice',content:'I prefer no water on my desk.\nPrivate second line.',created_at:now,source:'user',updated_at:null,expires_at:'2027-01-01T00:00:00+00:00',memory_scope:'home',revision:'c'.repeat(64)};
const descriptor = {kind:'http_json',display_target:'https://model.example/v1/respond (model fixture)',revision:'d'.repeat(64)};
const assessment = {allowed:true,ahimsa_score:1,aparigraha_score:1,risk_level:'low',reasons:['No harmful action.'],safer_alternative:null};
const clone = x => JSON.parse(JSON.stringify(x));
const basePreview = () => ({protocol:1,user_id:'alice',input:elements.question.value.trim(),memory_scope:'home',context_at:now,request_revision:'a'.repeat(64),corpus_revision:'b'.repeat(64),blocked:false,ethical_assessment:clone(assessment),canonical_evidence:[{entry:clone(source),revision:'e'.repeat(64)},{entry:{...clone(source),entry_id:'unselected',principle:'Other principle'},revision:'f'.repeat(64)}],memories:[clone(memory),{...clone(memory),memory_id:8,content:'Private unselected memory',revision:'8'.repeat(64)}],configured_reasoner:clone(descriptor),limits:['Unverified sample sources, not source quotations.']});
let currentPreview = basePreview(), responder = null, cancelCount = 0;
const response = (data, status = 200, declared = null) => {
  const bytes = new TextEncoder().encode(JSON.stringify(data)); let sent = false;
  return {ok:status >= 200 && status < 300,status,headers:{get:() => declared === null ? String(bytes.length) : declared},body:{getReader:() => ({read:async () => sent ? {done:true} : (sent=true,{done:false,value:bytes}),cancel:async () => {cancelCount += 1;},releaseLock:() => {}})}};
};
function eligibleEvidenceFixture() {
  for (const item of currentPreview.canonical_evidence) Object.assign(item.entry, {work:'Original test work',edition:'Original test edition',location:'Original test section',license:'Original synthetic fixture',verified:true});
}
function mockWholePassages(entries) {
  const output=['Selected source passages, not an answer. Their relevance, truth and support for any conclusion have not been established. These are complete admitted passages, not necessarily complete documents. Review, edition and licensing remain operator declarations.'];
  if(!entries.length)output.push('No source passages selected.');
  for(const e of entries){
    output.push(`[${e.entry_id}] ${e.work}; ${e.source}; ${e.location}; language: ${e.language}; edition: ${e.edition}; license: ${e.license}.`, 'Full selected passage:',e.principle);
    output.push(e.source_sha256 === undefined ? 'Source integrity: record-only excerpt matching; no backing source-file bytes were checked.' : `Source bytes checked at admission: SHA-256 ${e.source_sha256}; UTF-8 byte range [${e.source_byte_start}, ${e.source_byte_end}). This checks local byte identity, not authorship, edition authenticity, rights, scholarship or support for the answer.`);
  }
  return output.join('\n');
}
function answerData(body) {
  return {request_id:'fixture',user_id:body.user_id,input:body.input,memory_scope:body.memory_scope,response:body.reasoner_mode === 'evidence_only' ? mockWholePassages(body.sources.map(ref => currentPreview.canonical_evidence.find(s => s.entry.entry_id === ref.entry_id).entry)) : 'A selected-context answer.',ethical_assessment:clone(assessment),perspectives:[],action:null,created_at:now,
    canonical_evidence:body.sources.map(ref => clone(currentPreview.canonical_evidence.find(s => s.entry.entry_id === ref.entry_id).entry)),
    memories_used:body.memories.map(ref => clone(currentPreview.memories.find(m => m.memory_id === ref.memory_id))),
    context_review:{...(body.reasoner_mode === 'evidence_only' ? {output_contract:'whole_passages_v1'} : {}),protocol:1,reasoner_mode:body.reasoner_mode,request_revision:body.expected_request_revision,corpus_revision:body.expected_corpus_revision,sources:clone(body.sources),memories:clone(body.memories),selected_at:now,configured_reasoner:body.reasoner_mode === 'configured' ? clone(currentPreview.configured_reasoner) : null}};
}
async function normal(url, options) {
  const route = new URL(url).pathname;
  if (route === '/health') return response({context_review_protocol:1,context_evidence_protocol:1});
  assert.equal(options.method, 'POST'); assert.equal(options.headers.Authorization, 'Bearer ' + token);
  const body = JSON.parse(options.body);
  if (route === '/v1/context/preview') {
    assert.deepEqual(Object.keys(body).sort(), ['input','memory_scope','user_id']);
    assert.equal(body.user_id,'alice'); assert.equal(body.memory_scope,'home'); assert.equal(body.input,elements.question.value.trim());
    return response(currentPreview);
  }
  if (route === '/v1/context/answer') {
    assert.equal(body.confirm_context,true); assert.ok(!('learn' in body)); assert.ok(!('context' in body));
    assert.equal(body.expected_request_revision,currentPreview.request_revision); assert.equal(body.expected_corpus_revision,currentPreview.corpus_revision);
    if (body.reasoner_mode === 'configured') assert.equal(body.expected_reasoner_revision,currentPreview.configured_reasoner.revision);
    else assert.ok(!('expected_reasoner_revision' in body));
    return response(answerData(body));
  }
  throw new Error('Unexpected route ' + route);
}
const sandbox = {document:{querySelector:q => {assert.ok(elements[q.slice(1)],q);return elements[q.slice(1)];},createElement:t => new Element(t),createTextNode:t => ({textContent:t})},
  window:{addEventListener:(event, fn) => events[event] = fn}, URL, TextEncoder, TextDecoder, Uint8Array, AbortController,
  fetch:async (url, options) => {calls.push({url,options}); return actual ? fetch(url, options) : responder ? responder(url, options) : normal(url, options);}};
vm.createContext(sandbox); vm.runInContext(fs.readFileSync(path.join(root,'web/context-review.js'),'utf8'),sandbox);
const click = async id => elements[id].onclick();
const tick = async () => {for (let i=0;i<20;i++) await Promise.resolve();};
const deferred = () => {let resolve, reject; return {promise:new Promise((r,j) => {resolve=r;reject=j;}),get resolve(){return resolve;},get reject(){return reject;}};};
const previewCalls = () => calls.filter(c => c.url.endsWith('/v1/context/preview'));
const answerCalls = () => calls.filter(c => c.url.endsWith('/v1/context/answer'));
const listText = id => elements[id].children.map(e => e.textContent || e.children.map(c => c.textContent).join('\n')).join('\n');
const getChoices = () => vm.runInContext('choices',sandbox);
function select(kind, index = 0, checked = true) {const c=getChoices().filter(c=>c.kind===kind)[index];c.checkbox.checked=checked;c.checkbox.onchange();}
function confirm() {elements.confirm.checked=true;elements.confirm.onchange();}
async function open() {await click('preview');assert.equal(elements.review.hidden,false,elements.status.textContent);}
function resetFixture() {responder=null;elements.user.value='alice';elements.api.value='http://127.0.0.1:8787';elements.user.oninput();elements.token.value=token;elements.token.oninput();elements.scope.value='home';elements.scope.oninput();elements.question.value=question;elements.question.oninput();currentPreview=basePreview();}
async function actualChange(route, method, body) {const r=await fetch(elements.api.value+route,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)});assert.equal(r.status,200);return r.json();}
(async () => {
  assert.equal(calls.length,0); assert.equal(elements.mode.value,'local'); assert.equal(elements.confirm.checked,false); assert.equal(elements.answer.disabled,true);
  if (scenario === 'retained_draft_identity_guard') {
    for (const stage of ['draft','reviewed','answered']) {
      resetFixture(); if(stage!=='draft') await open(); if(stage==='answered'){confirm();await click('answer');}
      const before=calls.length; elements.api.value='http://127.0.0.1:9999'; await click('preview');
      assert.equal(calls.length,before); assert.equal(elements.token.value,''); assert.equal(elements.question.value,''); assert.equal(elements.review.hidden,true); assert.equal(elements.result.hidden,true);
    }
  } else if (scenario === 'resets_cannot_rebind_token') {
    for (const trigger of ['cancel','scope','question','token']) {
      for(const event of ['oninput','onchange']) {
        resetFixture(); await open(); elements.api.value='http://127.0.0.1:9999';
        if(trigger==='cancel')await click('cancel');else elements[trigger][event]();
        assert.equal(elements.token.value,''); assert.equal(elements.question.value,''); const before=calls.length;
        elements.question.value=question; await click('preview'); assert.equal(calls.length,before);
      }
    }
    resetFixture(); await open(); assert.equal(elements.review.hidden,false);
  } else if (scenario === 'restored_confirmation_rejected') {
    await open(); elements.confirm.checked=true; await click('answer'); assert.equal(answerCalls().length,0); assert.equal(calls.length,2); assert.equal(elements.confirm.checked,false);
    await open(); confirm(); await click('answer'); assert.equal(answerCalls().length,1);
  } else if (scenario === 'silent_selection_mode_rejected') {
    for (const change of ['mode','memory','source']) {
      resetFixture(); await open(); confirm(); const before=calls.length;
      if(change==='mode')elements.mode.value='configured';else getChoices().find(c=>c.kind===change).checkbox.checked=true;
      await click('answer'); assert.equal(calls.length,before); assert.equal(elements.confirm.checked,false); assert.equal(elements.review.hidden,true);
    }
  } else if (scenario === 'silent_mode_during_health_rejected') {
    await open(); select('memory'); confirm(); const hold=deferred(); responder=()=>hold.promise;
    const pending=click('answer'); await tick(); elements.mode.value='configured'; hold.resolve(response({context_review_protocol:1,context_evidence_protocol:1})); await pending;
    assert.equal(answerCalls().length,0); assert.equal(elements.review.hidden,true); assert.equal(elements.confirm.checked,false);
  } else if (scenario === 'stream_stops_at_first_stale_chunk') {
    for (const route of ['/health','/v1/context/preview','/v1/context/answer']) {
      resetFixture(); if(route.endsWith('answer')){await open();confirm();}
      const hold=deferred(); let reads=0,cancelled=false;
      responder=(url,options)=>url.endsWith(route)?{ok:true,headers:{get:()=>null},body:{getReader:()=>({read:async()=>{reads++;return reads===1?hold.promise:{done:true};},cancel:async()=>{cancelled=true;},releaseLock:()=>{}})}}:normal(url,options);
      const pending=click(route.endsWith('answer')?'answer':'preview'); await tick(); assert.equal(reads,1);
      elements.api.value='http://127.0.0.1:9999'; hold.resolve({done:false,value:new TextEncoder().encode('{}')}); await pending;
      assert.equal(reads,1); assert.equal(cancelled,true); assert.equal(elements.token.value,''); assert.equal(elements.question.value,''); assert.equal(elements.result.hidden,true);
    }
  } else if (scenario === 'preview_only_unchecked') {
    await open(); assert.equal(previewCalls().length,1); assert.equal(answerCalls().length,0);
    assert.ok(getChoices().every(c=>!c.checkbox.checked)); assert.equal(elements.mode.value,'local'); assert.equal(elements.confirm.checked,false);
    assert.match(listText('sources'),/Full principle/); assert.match(listText('memories'),/Private second line/); assert.match(listText('memories'),/Recall expiry: 2027/);
    await click('answer'); assert.equal(answerCalls().length,0);
  } else if (scenario === 'evidence_success_and_inert_text') {
    eligibleEvidenceFixture();
    assert.ok(html.includes('value="evidence_only"')); assert.ok(html.includes('Passages only, not an answer'));
    const payload='<img src=x onerror=alert(1)>\n<script>inert</script>\n'+'complete '.repeat(1500);
    currentPreview.canonical_evidence[0].entry.principle=payload;
    await open();select('source');confirm();elements.mode.value='evidence_only';elements.mode.onchange();
    assert.equal(elements.confirm.checked,false);assert.match(elements['consent-text'].textContent,/not a generated answer/);
    await click('answer');assert.equal(answerCalls().length,0);confirm();const pending=click('answer');await click('answer');await pending;
    assert.equal(answerCalls().length,1);const body=JSON.parse(answerCalls()[0].options.body);
    assert.equal(body.reasoner_mode,'evidence_only');assert.deepEqual(body.memories,[]);assert.ok(!('expected_reasoner_revision' in body));
    assert.equal(elements.result.hidden,false,elements.status.textContent);assert.ok(elements.response.textContent.includes(payload));assert.equal(elements.response.children.length,0);
    assert.match(elements['result-title'].textContent,/not an answer/);assert.match(elements.status.textContent,/Not an answer/);
    await open();elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
    assert.equal(elements.result.hidden,false,elements.status.textContent);assert.match(elements.response.textContent,/No source passages selected/);
  } else if (scenario === 'evidence_utf8_byte_binding_and_invalid_sources') {
    eligibleEvidenceFixture();const entry=currentPreview.canonical_evidence[0].entry;
    entry.principle='  हिन्दी નોંધ\r\n😀 Repeated. Repeated.\r\n  ';entry.source_sha256='a'.repeat(64);entry.source_byte_start=7;entry.source_byte_end=7+new TextEncoder().encode(entry.principle).length;
    await open();select('source');elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
    assert.equal(elements.result.hidden,false,elements.status.textContent);assert.ok(elements.response.textContent.includes(entry.principle));assert.ok(elements.response.textContent.includes(`[7, ${entry.source_byte_end})`));
    const invalid=[e=>e.verified=false,e=>e.edition=null,e=>e.principle+='\u0000',e=>e.principle+='\ud800',e=>e.entry_id='bad[id]',e=>Object.assign(e,{source_sha256:'b'.repeat(64),source_byte_start:0,source_byte_end:1})];
    for(const change of invalid){resetFixture();eligibleEvidenceFixture();change(currentPreview.canonical_evidence[0].entry);await open();
      if(elements.review.hidden)continue;select('source');elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
      assert.equal(elements.result.hidden,true,change.toString());assert.equal(elements.response.textContent,'');}
  } else if (scenario === 'evidence_memory_selection_rejected') {
    await open();select('memory');elements.mode.value='evidence_only';elements.mode.onchange();confirm();const before=calls.length;
    await click('answer');assert.equal(calls.length,before);assert.equal(answerCalls().length,0);assert.match(elements.status.textContent,/cannot use private memories/);assert.equal(elements.result.hidden,true);
  } else if (scenario === 'evidence_receipt_and_contract_tampering') {
    const mutations=[d=>delete d.context_review.output_contract,d=>d.context_review.output_contract='other',d=>d.context_review.reasoner_mode='local',
      d=>d.context_review.configured_reasoner=clone(descriptor),d=>d.context_review.sources[0].revision='0'.repeat(64),
      d=>d.context_review.memories=[{memory_id:7,revision:memory.revision}],d=>d.memories_used=[clone(memory)],
      d=>d.perspectives=['generated'],d=>delete d.perspectives,d=>d.perspectives=null,d=>d.action={},d=>d.canonical_evidence[0].principle='truncated',d=>d.response=d.response.slice(0,100),d=>d.response+='\nA generated claim.',d=>d.response=d.response.replace('Full selected passage:','Summary:')];
    for(const mutate of mutations){resetFixture();eligibleEvidenceFixture();await open();select('source');elements.mode.value='evidence_only';elements.mode.onchange();confirm();
      responder=(u,o)=>{if(!u.endsWith('/v1/context/answer'))return normal(u,o);const d=answerData(JSON.parse(o.body));mutate(d);return response(d);};
      await click('answer');assert.equal(elements.result.hidden,true,mutate.toString());assert.equal(elements.response.textContent,'');}
  } else if (scenario === 'evidence_mode_boundaries') {
    for(const silent of [false,true]){resetFixture();await open();elements.mode.value='evidence_only';elements.mode.onchange();confirm();elements.mode.value='local';if(!silent)elements.mode.onchange();
      await click('answer');assert.equal(answerCalls().length,0);assert.equal(elements.confirm.checked,false);}
    resetFixture();await open();elements.mode.value='evidence_only';elements.mode.onchange();confirm();const hold=deferred();responder=()=>hold.promise;
    const pending=click('answer');await tick();elements.mode.value='evidence_only';hold.resolve(response({context_review_protocol:1,context_evidence_protocol:1}));await pending;
    assert.equal(answerCalls().length,0);assert.equal(elements.result.hidden,true);
  } else if (scenario === 'evidence_health_and_failure_no_fallback') {
    for(const failure of ['old_api','rejected']){resetFixture();await open();elements.mode.value='evidence_only';elements.mode.onchange();confirm();const before=answerCalls().length;
      responder=(u,o)=>u.endsWith('/health')&&failure==='old_api'?response({context_review_protocol:1}):u.endsWith('/v1/context/answer')?response({},400):normal(u,o);
      await click('answer');assert.equal(answerCalls().length,before+(failure==='old_api'?0:1));assert.equal(elements.result.hidden,true);await click('answer');assert.equal(answerCalls().length,before+(failure==='old_api'?0:1));}
  } else if (scenario === 'selected_only_local_and_consumed') {
    await open(); select('source'); select('memory'); confirm(); const pending=click('answer');
    assert.equal(elements.confirm.checked,false); await click('answer'); await pending;
    assert.equal(answerCalls().length,1); const body=JSON.parse(answerCalls()[0].options.body);
    assert.equal(body.reasoner_mode,'local'); assert.deepEqual(body.sources,[{entry_id:'gentle',revision:'e'.repeat(64)}]); assert.deepEqual(body.memories,[{memory_id:7,revision:'c'.repeat(64)}]);
    assert.ok(!answerCalls()[0].options.body.includes('Private')); assert.equal(elements.result.hidden,false); assert.equal(elements.review.hidden,true);
    assert.ok(!listText('used-memories').includes('unselected')); assert.ok(!listText('used-sources').includes('Other principle')); assert.match(elements.receipt.textContent,/provider was not used/);
    confirm(); await click('answer'); assert.equal(answerCalls().length,1);
    for (const c of calls) {assert.equal(c.options.redirect,'error');assert.equal(c.options.credentials,'omit');assert.equal(c.options.cache,'no-store');assert.ok(c.options.signal);if(c.url.endsWith('/health'))assert.ok(!c.options.headers.Authorization);}
  } else if (scenario === 'configured_explicit_and_empty_selection') {
    await open(); confirm(); elements.mode.value='configured'; elements.mode.onchange(); assert.equal(elements.confirm.checked,false);
    assert.match(elements['consent-text'].textContent,/provider receives this material/); assert.match(elements.target.textContent,/model.example/);
    await click('answer');assert.equal(answerCalls().length,0);confirm();await click('answer');
    assert.equal(elements.result.hidden,false,elements.status.textContent);const body=JSON.parse(answerCalls()[0].options.body);
    assert.equal(body.reasoner_mode,'configured');assert.deepEqual(body.sources,[]);assert.deepEqual(body.memories,[]);assert.equal(body.expected_reasoner_revision,descriptor.revision);
    await open();assert.equal(elements.mode.value,'local');assert.equal(elements.confirm.checked,false);
  } else if (scenario === 'selection_invalidates_consent') {
    await open();confirm();select('source');assert.equal(elements.confirm.checked,false);assert.equal(elements.answer.disabled,true);
    confirm();select('memory');assert.equal(elements.confirm.checked,false);confirm();select('memory',0,false);assert.equal(elements.confirm.checked,false);
  } else if (scenario === 'changes_clear_private_context') {
    for (const field of ['user','api','token','scope','question']) {
      resetFixture();await open();select('memory');confirm();
      elements[field].value={user:'bob',api:'https://other.example',token:'b'.repeat(40),scope:'work',question:'New question'}[field];elements[field].oninput();
      assert.equal(elements.review.hidden,true);assert.equal(elements.result.hidden,true);assert.equal(elements.memories.children.length,0);assert.equal(elements.sources.children.length,0);assert.equal(elements.confirm.checked,false);assert.equal(elements.mode.value,'local');assert.equal(elements.answer.disabled,true);
      if(['user','api'].includes(field))assert.equal(elements.token.value,'');
      if(['user','api','token'].includes(field))assert.equal(elements.question.value,'');
    }
    resetFixture();await open();confirm();events.pagehide();assert.equal(elements.token.value,'');assert.equal(elements.question.value,'');
    elements.token.value=token;elements.question.value=question;elements.confirm.checked=true;events.pageshow();assert.equal(elements.token.value,'');assert.equal(elements.question.value,'');assert.equal(elements.confirm.checked,false);
  } else if (scenario === 'stale_health_boundary') {
    for (const kind of ['preview','answer']) {
      resetFixture();if(kind==='answer'){await open();confirm();}
      const before=answerCalls().length+previewCalls().length,hold=deferred();responder=()=>hold.promise;const pending=click(kind);await tick();
      elements.api.value='https://other.example';elements.api.oninput();hold.resolve(response({context_review_protocol:1,context_evidence_protocol:1}));await pending;
      assert.equal(answerCalls().length+previewCalls().length,before);assert.equal(elements.token.value,'');assert.equal(elements.question.value,'');assert.equal(elements.review.hidden,true);
    }
  } else if (scenario === 'stale_preview_response') {
    for(const field of ['user','scope','question']) {
      resetFixture();const hold=deferred();responder=(u,o)=>u.endsWith('/v1/context/preview')?hold.promise:normal(u,o);
      const pending=click('preview');await tick();assert.equal(calls[calls.length-1].url.endsWith('/v1/context/preview'),true);
      elements[field].value='changed';elements[field].oninput();hold.resolve(response(currentPreview));await pending;
      assert.equal(elements.review.hidden,true);assert.equal(elements.memories.children.length,0);
    }
  } else if (scenario === 'stale_stream_body') {
    const hold=deferred();responder=(u,o)=>u.endsWith('/v1/context/preview')?{ok:true,headers:{get:()=>null},body:{getReader:()=>({read:()=>hold.promise,cancel:async()=>{},releaseLock:()=>{}})}}:normal(u,o);
    const pending=click('preview');await tick();elements.user.value='bob';elements.user.oninput();hold.resolve({done:true});await pending;
    assert.equal(elements.review.hidden,true);assert.equal(elements.token.value,'');assert.equal(elements.question.value,'');
  } else if (scenario === 'silent_field_changes_fail_closed') {
    await open();select('memory');confirm();elements.question.value='Silently changed';await click('answer');assert.equal(answerCalls().length,0);assert.equal(elements.review.hidden,true);
    resetFixture();const hold=deferred();responder=(u,o)=>u.endsWith('/v1/context/preview')?hold.promise:normal(u,o);
    const pending=click('preview');await tick();elements.user.value='bob';hold.resolve(response(currentPreview));await pending;
    assert.equal(elements.token.value,'');assert.equal(elements.question.value,'');assert.equal(elements.review.hidden,true);
  } else if (scenario === 'cancel_preview_and_answer') {
    for(const kind of ['preview','answer']) {
      resetFixture();if(kind==='answer'){await open();select('memory');confirm();}
      const hold=deferred();let body;responder=(u,o)=>u.endsWith('/v1/context/'+kind)?(body=o.body,hold.promise):normal(u,o);
      const pending=click(kind);await tick();const request=calls[calls.length-1];await click('cancel');assert.equal(request.options.signal.aborted,true);
      if(kind==='answer')assert.match(elements.status.textContent,/may already have reached/);
      hold.resolve(response(kind==='preview'?currentPreview:answerData(JSON.parse(body))));await pending;
      assert.equal(elements.review.hidden,true);assert.equal(elements.result.hidden,true);assert.equal(elements.question.value,'');
    }
  } else if (scenario === 'stale_answer_changes') {
    for(const field of ['scope','question','user','token','api']) {
      resetFixture();await open();select('memory');confirm();const hold=deferred();let body;
      responder=(u,o)=>u.endsWith('/v1/context/answer')?(body=JSON.parse(o.body),hold.promise):normal(u,o);
      const pending=click('answer');await tick();elements[field].value='changed';elements[field].oninput();hold.resolve(response(answerData(body)));await pending;
      assert.equal(elements.result.hidden,true);assert.equal(elements.response.textContent,'');assert.equal(elements['used-memories'].children.length,0);
    }
  } else if (scenario === 'failed_answer_no_retry') {
    for(const failure of ['transport','409','500','malformed']) {
      resetFixture();await open();select('memory');confirm();const before=answerCalls().length;
      responder=(u,o)=>u.endsWith('/v1/context/answer')?(failure==='transport'?Promise.reject(new Error('connection lost')):response(failure==='malformed'?{}:{},failure==='409'?409:failure==='500'?500:200)):normal(u,o);
      await click('answer');confirm();await click('answer');assert.equal(answerCalls().length,before+1);assert.equal(elements.review.hidden,true);assert.equal(elements.result.hidden,true);assert.match(elements.status.textContent,/may already have reached/);
      if(failure==='409')assert.match(elements.status.textContent,/Refresh/);
    }
  } else if (scenario === 'answer_binding_rejects_tampering') {
    const mutations=[
      d=>d.user_id='bob',d=>d.input='other',d=>d.memory_scope='work',d=>d.action={action:'move'},
      d=>d.context_review.protocol=2,d=>d.context_review.reasoner_mode='configured',d=>d.context_review.request_revision='0'.repeat(64),d=>d.context_review.corpus_revision='0'.repeat(64),
      d=>d.context_review.sources[0].revision='0'.repeat(64),d=>d.context_review.memories[0].revision='0'.repeat(64),d=>d.context_review.sources=[],d=>d.context_review.memories=[],
      d=>d.canonical_evidence[0].principle='Changed content under same revision',d=>d.memories_used[0].content='Changed private context',d=>d.memories_used[0].expires_at=null,
      d=>d.canonical_evidence=[],d=>d.memories_used=[],d=>d.canonical_evidence.push(clone(currentPreview.canonical_evidence[1].entry)),d=>d.memories_used.push(clone(currentPreview.memories[1])),
      d=>d.context_review.configured_reasoner=clone(descriptor),d=>d.context_review.selected_at='bad',d=>d.ethical_assessment.allowed=false,
    ];
    for(const mutate of mutations) {
      resetFixture();await open();select('source');select('memory');confirm();responder=(u,o)=>{if(!u.endsWith('/v1/context/answer'))return normal(u,o);const d=answerData(JSON.parse(o.body));mutate(d);return response(d);};
      await click('answer');assert.equal(elements.result.hidden,true,mutate.toString());assert.equal(elements.response.textContent,'');assert.equal(elements.review.hidden,true);
    }
  } else if (scenario === 'configured_target_binding') {
    for(const change of ['revision','display_target','kind']) {
      resetFixture();await open();select('memory');elements.mode.value='configured';elements.mode.onchange();confirm();
      responder=(u,o)=>{if(!u.endsWith('/v1/context/answer'))return normal(u,o);const d=answerData(JSON.parse(o.body));d.context_review.configured_reasoner[change]=change==='revision'?'0'.repeat(64):change==='kind'?'local':'https://other.example/model';return response(d);};
      await click('answer');assert.equal(elements.result.hidden,true);assert.match(elements.status.textContent,/configured target/);
    }
  } else if (scenario === 'invalid_preview_rejected') {
    const mutations=[d=>d.protocol=2,d=>d.user_id='bob',d=>d.input='other',d=>d.memory_scope='work',d=>d.request_revision='bad',d=>d.corpus_revision='bad',d=>d.context_at=null,
      d=>d.canonical_evidence.push(clone(d.canonical_evidence[0])),d=>d.memories.push(clone(d.memories[0])),d=>d.memories[0].user_id='bob',d=>d.memories[0].memory_scope='work',d=>d.memories[0].revision='bad',
      d=>delete d.memories[0].expires_at,d=>d.memories[0].expires_at='not a timestamp',d=>d.memories[0].expires_at='2027-02-30T00:00:00Z',d=>d.memories[0].expires_at='2027-01-01T00:00:00-00:00',d=>d.memories[0].expires_at='0001-01-01T00:00:00+01:00',d=>d.canonical_evidence[0].revision='bad',d=>delete d.canonical_evidence[0].entry.principle,
      d=>d.canonical_evidence[0].entry.source_sha256='0'.repeat(64),d=>d.canonical_evidence[0].entry.hidden_context='not shown',d=>d.configured_reasoner.kind='unknown',d=>d.configured_reasoner.revision='bad',d=>d.blocked=true];
    for(const mutate of mutations) {resetFixture();mutate(currentPreview);await click('preview');assert.equal(elements.review.hidden,true,mutate.toString());assert.equal(elements.memories.children.length,0);assert.equal(elements.answer.disabled,true);}
  } else if (scenario === 'blocked_and_unavailable') {
    currentPreview.blocked=true;currentPreview.ethical_assessment.allowed=false;currentPreview.canonical_evidence=[];currentPreview.memories=[];
    await open();assert.equal(elements.answer.disabled,true);confirm();await click('answer');assert.equal(answerCalls().length,0);assert.match(elements.status.textContent,/blocked/);
    resetFixture();currentPreview.configured_reasoner.kind='unavailable';await open();assert.equal(elements['configured-option'].disabled,true);
    elements.mode.value='configured';elements.mode.onchange();confirm();await click('answer');assert.equal(answerCalls().length,0);
    await open();confirm();await click('answer');assert.equal(answerCalls().length,1);assert.equal(elements.result.hidden,false,elements.status.textContent);
  } else if (scenario === 'untrusted_text_and_source_digest') {
    const payload='<img src=x onerror=alert(1)>\n<script>private</script>';
    currentPreview.canonical_evidence[0].entry.principle=payload;currentPreview.canonical_evidence[0].entry.source_sha256='7'.repeat(64);currentPreview.canonical_evidence[0].entry.source_byte_start=1;currentPreview.canonical_evidence[0].entry.source_byte_end=100;
    currentPreview.memories[0].content=payload;currentPreview.configured_reasoner.display_target=payload;currentPreview.limits=[payload];
    await open();assert.ok(listText('sources').includes(payload));assert.ok(listText('sources').includes('7'.repeat(64)));assert.ok(listText('memories').includes(payload));assert.equal(elements.limits.children[0].textContent,payload);assert.ok(elements.target.textContent.includes(payload));
    select('source');select('memory');confirm();responder=(u,o)=>u.endsWith('/v1/context/answer')?response({...answerData(JSON.parse(o.body)),response:payload}):normal(u,o);
    await click('answer');assert.equal(elements.response.textContent,payload);assert.equal(elements.response.children.length,0);assert.ok(listText('used-sources').includes(payload));
  } else if (scenario === 'bounds_and_protocol') {
    for(const api of ['http://example.com','https://user:pass@example.com','https://example.com/path','https://example.com?token=abc','https://exa\nmple.com']) {elements.api.value=api;await click('preview');assert.equal(calls.length,0);}
    resetFixture();for(const scope of ['Home','home\n',' home']) {elements.scope.value=scope;await click('preview');assert.equal(calls.length,0);}
    resetFixture();for(const input of ['','   ','x'.repeat(10001)]) {elements.question.value=input;await click('preview');assert.equal(calls.length,0);}
    resetFixture();responder=()=>response({});await click('preview');assert.equal(previewCalls().length,0);assert.match(elements.status.textContent,/protocol/);
    for(const declared of ['1','70000']) {resetFixture();responder=(u,o)=>u.endsWith('/v1/context/preview')?response({data:'x'.repeat(65537)},200,declared):normal(u,o);await click('preview');assert.equal(elements.review.hidden,true);assert.match(elements.status.textContent,/limit/);}
    assert.equal(cancelCount,1);
  } else if (scenario === 'real_evidence_selected_or_empty') {
    await open();select('source');const passage=getChoices().find(c=>c.kind==='source').value.entry.principle;
    elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
    assert.equal(elements.result.hidden,false,elements.status.textContent);assert.ok(elements.response.textContent.includes(passage));assert.match(elements.response.textContent,/Selected source passages, not an answer/);
    assert.deepEqual(JSON.parse(answerCalls()[0].options.body).memories,[]);assert.equal(elements['used-memories'].children.length,1);
    await open();elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
    assert.equal(elements.result.hidden,false,elements.status.textContent);assert.match(elements.response.textContent,/No source passages selected/);assert.equal(answerCalls().length,2);
  } else if (scenario === 'real_evidence_ineligible') {
    await open();select('source');elements.mode.value='evidence_only';elements.mode.onchange();confirm();await click('answer');
    assert.equal(elements.result.hidden,true);assert.match(elements.status.textContent,/400/);assert.equal(answerCalls().length,1);
    await click('answer');assert.equal(answerCalls().length,1);
  } else if (scenario === 'real_selected_local') {
    await open();assert.ok(getChoices().some(c=>c.kind==='memory'));assert.equal(answerCalls().length,0);assert.ok(getChoices().every(c=>!c.checkbox.checked));
    select('memory');if(getChoices().some(c=>c.kind==='source'))select('source');confirm();await click('answer');assert.equal(elements.result.hidden,false,elements.status.textContent);assert.equal(answerCalls().length,1);assert.match(elements.receipt.textContent,/provider was not used/);
    assert.ok(!listText('used-memories').includes('Unrelated Bob'));assert.ok(!listText('used-memories').includes('Unrelated work'));
  } else if (scenario === 'long_source_metadata') {
    currentPreview.canonical_evidence[0].entry.principle='Full passage '+ 'x'.repeat(19900);
    currentPreview.configured_reasoner.display_target='https://model.example (model: '+ 'm'.repeat(2100)+')';
    await open();assert.ok(listText('sources').includes(currentPreview.canonical_evidence[0].entry.principle));assert.ok(elements.target.textContent.includes(currentPreview.configured_reasoner.display_target));
  } else if (scenario === 'real_expired_memory_conflict') {
    await open();const m=getChoices().find(c=>c.kind==='memory').value;select('memory');
    await actualChange('/v1/memory-expiration','PATCH',{memory_id:m.memory_id,expires_at:'2000-01-01T00:00:00Z'});confirm();await click('answer');
    assert.equal(elements.result.hidden,true);assert.equal(elements.review.hidden,true);assert.match(elements.status.textContent,/Refresh/);assert.equal(answerCalls().length,1);
  } else if (scenario === 'real_wrong_owner') {
    elements.token.value='test-bob-'+'b'.repeat(32);elements.token.oninput();elements.question.value=question;await click('preview');
    assert.equal(elements.review.hidden,true);assert.match(elements.status.textContent,/403/);assert.equal(answerCalls().length,0);
  } else if (scenario === 'real_changed_memory_conflict') {
    await open();const m=getChoices().find(c=>c.kind==='memory').value;select('memory');
    await actualChange('/v1/memory','PATCH',{memory_id:m.memory_id,content:'I prefer a changed cleaning method'});confirm();await click('answer');
    assert.equal(elements.result.hidden,true);assert.equal(elements.review.hidden,true);assert.match(elements.status.textContent,/Refresh/);assert.equal(answerCalls().length,1);
    await click('answer');assert.equal(answerCalls().length,1);
  } else throw new Error('Unknown scenario ' + scenario);
  console.log('PASS ' + scenario);
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
