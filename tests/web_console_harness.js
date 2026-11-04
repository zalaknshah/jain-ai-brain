// Deterministic script harness, not proof of real microphone/browser support.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const scenario = process.argv[2], actual=scenario.startsWith('real_');
const elements = {};
for (const id of ['input','answer','memory-scope','status','meta small','api','token','learn','user','listen','stop','send','cancel','read','language','speak-replies']) {
  elements['#' + id] = {value:'', checked:false, disabled:false, textContent:''};
}
const el = id => elements['#' + id];
el('memory-scope').value='default';
el('input').value='Remember that I prefer quiet rooms';
el('api').value=actual?process.env.JACE_TEST_API:'http://localhost'; el('token').value=(actual?'test-alice-':'synthetic-fixture-')+ 'a'.repeat(32);
if(actual){const url=new URL(el('api').value);assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');} el('user').value='alice'; el('language').value='en-IN';
let requests=[], sent=[], fetched=[], recognizers=[], voices=[{lang:'en-US'}], spoken=[], cancelled=0, startFails=false;
let fetchImpl=actual?fetch:async()=>reply('Fixture response');
let capabilityImpl=actual?fetch:async()=>response({memory_scope_protocol:1});
const flush=()=>new Promise(done=>setImmediate(done));
const listeners={};
const window={addEventListener:(name, fn)=>listeners[name]=fn};
class Recognition {
  constructor(){recognizers.push(this); this.started=0; this.stopped=0; this.aborted=0;}
  start(){if(startFails)throw new Error('fixture unavailable');this.started++;}
  stop(){this.stopped++;}
  abort(){this.aborted++;}
}
if (scenario !== 'unsupported') {
  window.SpeechRecognition=Recognition;
  window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
  window.speechSynthesis={getVoices:()=>voices,speak:item=>spoken.push(item),cancel:()=>cancelled++};
}
function response(data, ok=true) {
  const bytes=new TextEncoder().encode(JSON.stringify(data));let sent=false;
  return {ok,status:ok?200:500,headers:{get:()=>String(bytes.length)},body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:async()=>{},releaseLock:()=>{}})}};
}
function reply(text, scope=el('memory-scope').value){return response({user_id:el('user').value,input:el('input').value.trim(),memory_scope:scope,response:text,ethical_assessment:{risk_level:'low'},perspectives:[],canonical_evidence:[]});}
const context=vm.createContext({window,AbortController,URL,TextEncoder,TextDecoder,Uint8Array,document:{querySelector:id=>elements[id]},fetch:(url, request)=>{
  requests.push({url,request});
  if(request.method==='GET') return capabilityImpl(url,request);
  sent.push(JSON.parse(request.body)); fetched.push(request); return fetchImpl(url,request);
}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/console.js'),'utf8'),context);
const call = code => vm.runInContext(code,context);
const result = text => ({results:[[{transcript:text}]]});
const checkLearn=()=>{el('learn').checked=true;el('learn').onchange();};
const deferred=()=>{let resolve;return{promise:new Promise(r=>resolve=r),get resolve(){return resolve;}};};
const restore=()=>{
  el('user').value='alice';el('api').value='http://localhost';el('api').onchange();el('memory-scope').value='default';el('memory-scope').onchange();
  el('token').value='synthetic-fixture-'+ 'a'.repeat(32);el('token').onchange();el('input').value='Remember that I prefer quiet rooms';
  fetchImpl=async()=>reply('Fixture response');capabilityImpl=async()=>response({memory_scope_protocol:1});
};
const changeIdentity=field=>{el(field).value=field==='api'?'https://different.example':field==='token'?'another-'+ 'z'.repeat(32):field==='user'?'bob':'work';};
const blank=()=>{assert.equal(el('input').value,'');assert.equal(el('read').disabled,true);assert.equal(el('learn').checked,false);assert.equal(el('meta small').textContent,'');assert.notEqual(el('answer').textContent,'PRIVATE');};
async function run(){
  if(scenario==='binding_retained_identity'){
    for(const field of ['user','api','token','memory-scope']){restore();checkLearn();const before=requests.length;changeIdentity(field);await call('ask()');assert.equal(requests.length,before);blank();if(field!=='memory-scope')assert.equal(el('token').value,'');}
  } else if(scenario==='binding_silent_health'){
    for(const field of ['user','api','token','memory-scope']){restore();const hold=deferred();capabilityImpl=()=>hold.promise;checkLearn();const before=sent.length,p=call('ask()');await flush();changeIdentity(field);hold.resolve(response({memory_scope_protocol:1}));await p;assert.equal(sent.length,before);blank();}
  } else if(scenario==='binding_silent_reply'){
    for(const field of ['user','api','token','memory-scope']){restore();const hold=deferred();fetchImpl=()=>hold.promise;el('speak-replies').checked=true;const before=spoken.length,p=call('ask()');await flush();changeIdentity(field);hold.resolve(reply('PRIVATE','default'));await p;blank();assert.equal(spoken.length,before);}
  } else if(scenario==='binding_transcript_identity'){
    for(const field of ['user','api','memory-scope']){restore();call('startListening()');const mic=recognizers.at(-1);changeIdentity(field);mic.onresult(result('PRIVATE'));mic.onend();blank();}
  } else if(scenario==='binding_transcript_draft'){
    call('startListening()');const mic=recognizers.at(-1);el('input').value='New typed question';mic.onresult(result('PRIVATE'));mic.onend();assert.equal(el('input').value,'New typed question');assert.equal(sent.length,0);
  } else if(scenario==='binding_read_identity'){
    await call('ask()');el('user').value='bob';call('readResponse()');assert.equal(spoken.length,0);blank();assert.equal(el('token').value,'');
  } else if(scenario==='binding_pending_playback_identity'){
    await call('ask()');call('startListening()');const mic=recognizers.at(-1);call('readResponse()');el('api').value='https://different.example';mic.onend();assert.equal(spoken.length,0);blank();assert.equal(el('token').value,'');
  } else if(scenario==='binding_reset_rebind'){
    for(const action of ['cancel','token','memory-scope']){restore();el('api').value='https://different.example';if(action==='cancel')call('stopReply()');else el(action).onchange();assert.equal(el('token').value,'');blank();const before=requests.length;el('input').value='New question';await call('ask()');assert.equal(requests.length,before);}
  } else if(scenario==='binding_learning_snapshot'){
    checkLearn();el('input').value='Remember that I prefer shorter answers';await call('ask()');assert.equal(requests.length,0);assert.equal(el('learn').checked,false);
    checkLearn();await call('ask()');assert.equal(sent.length,1);assert.equal(sent[0].learn,true);
    checkLearn();el('input').value='Another question';el('input').onchange();assert.equal(el('learn').checked,false);await call('ask()');assert.equal(sent[1].learn,false);
  } else if(scenario==='binding_restored_learning'){
    el('learn').checked=true;await call('ask()');assert.equal(requests.length,0);assert.equal(el('learn').checked,false);checkLearn();await call('ask()');assert.equal(sent[0].learn,true);
  } else if(scenario==='binding_page_lifecycle'){
    for(const event of ['pagehide','pageshow']){restore();await call('ask()');checkLearn();el('speak-replies').checked=true;listeners[event]();blank();assert.equal(el('token').value,'');assert.equal(el('speak-replies').checked,false);}
  } else if(scenario==='binding_question_during_health'){
    for(const fire of [false,true]){restore();const hold=deferred();capabilityImpl=()=>hold.promise;checkLearn();const before=sent.length,p=call('ask()');await flush();el('input').value='New question';if(fire)el('input').oninput();hold.resolve(response({memory_scope_protocol:1}));await p;assert.equal(sent.length,before);assert.equal(el('input').value,'New question');assert.equal(el('learn').checked,false);}
  } else if(scenario==='binding_stream_change'){
    for(const field of ['api','input']){restore();const hold=deferred(),started=deferred();let cancelled=false;fetchImpl=async()=>({ok:true,headers:{get:()=>null},body:{getReader:()=>({read:()=>{started.resolve();return hold.promise;},cancel:async()=>{cancelled=true;},releaseLock:()=>{}})}});
      const p=call('ask()');await started.promise;if(field==='api')changeIdentity(field);else el('input').value='New question';hold.resolve({done:false,value:new TextEncoder().encode('{}')});await p;assert.equal(cancelled,true);assert.equal(el('read').disabled,true);assert.notEqual(el('answer').textContent,'PRIVATE');assert.match(el('status').textContent,/may still finish/);}
  } else if(scenario==='binding_origin_validation'){
    for(const url of ['http://example.com','https://user:pass@example.com','https://example.com/path','https://example.com/?x=1','https://example.com/#x','https://exa\nmple.com',' https://example.com']){restore();el('api').value=url;el('api').onchange();el('token').value='synthetic-'+ 'a'.repeat(32);el('token').onchange();el('input').value='Question';const before=requests.length;await call('ask()');assert.equal(requests.length,before);}
  } else if(scenario==='binding_transport_options'){
    await call('ask()');for(const {request} of requests){assert.equal(request.redirect,'error');assert.equal(request.credentials,'omit');assert.equal(request.cache,'no-store');if(request.method==='GET')assert.ok(!request.headers.Authorization);}
  } else if(scenario==='binding_response_bounds'){
    capabilityImpl=async()=>response({memory_scope_protocol:1,pad:'x'.repeat(1024*1024)});await call('ask()');assert.equal(sent.length,0);assert.match(el('answer').textContent,/limit/);
    capabilityImpl=async()=>response({memory_scope_protocol:1});fetchImpl=async()=>({ok:true,headers:{get:()=>null},json:async()=>({response:'PRIVATE'})});await call('ask()');assert.match(el('answer').textContent,/Streaming/);assert.equal(el('read').disabled,true);
  } else if(scenario==='binding_reply_context'){
    for(const field of ['user_id','input']){restore();fetchImpl=async()=>response({user_id:'alice',input:el('input').value.trim(),memory_scope:'default',response:'PRIVATE',[field]:'wrong context'});await call('ask()');assert.equal(el('read').disabled,true);assert.match(el('answer').textContent,/question and owner/);assert.equal(spoken.length,0);}
  } else if(scenario==='binding_consumed_invalid_learning'){
    el('input').value='x'.repeat(10001);checkLearn();await call('ask()');assert.equal(requests.length,0);assert.equal(el('learn').checked,false);el('input').value='New question';await call('ask()');assert.equal(sent[0].learn,false);
  } else if(scenario==='binding_preflight_cancel'){
    const hold=deferred();capabilityImpl=()=>hold.promise;const p=call('ask()');call('stopReply()');hold.resolve(response({memory_scope_protocol:1}));await p;assert.equal(sent.length,0);assert.doesNotMatch(el('status').textContent,/may still finish/);
  } else if(scenario==='real_ask_learning'){
    el('memory-scope').value='home';el('memory-scope').onchange();el('input').value='Remember that I prefer blue shirts';checkLearn();await call('ask()');assert.equal(sent.length,1);assert.equal(sent[0].learn,true);assert.equal(el('read').disabled,false);
    await call('ask()');assert.equal(sent.length,2);assert.equal(sent[1].learn,false);assert.equal(el('read').disabled,false);
  } else if(scenario==='real_wrong_owner'){
    el('token').value='test-bob-'+ 'b'.repeat(32);el('token').onchange();el('input').value='Remember that I prefer blue shirts';checkLearn();await call('ask()');assert.equal(sent.length,1);assert.match(el('answer').textContent,/403/);assert.equal(el('read').disabled,true);
  } else
  if(scenario==='consent'){
    checkLearn(); await call('ask()'); await call('ask()');
    assert.strictEqual(sent[0].learn,true); assert.strictEqual(sent[1].learn,false);
    fetchImpl=async()=>{throw new Error('mock failure');}; checkLearn(); await call('ask()');
    fetchImpl=async()=>reply('next'); await call('ask()');
    assert.strictEqual(sent[2].learn,true); assert.strictEqual(sent[3].learn,false);
  } else if(scenario==='transcript'){
    el('language').value='hi-IN'; checkLearn(); call('startListening()');
    assert.strictEqual(recognizers[0].lang,'hi-IN');
    recognizers[0].onresult(result('मुझे करुणा पसंद है')); recognizers[0].onend();
    assert.strictEqual(el('input').value,'मुझे करुणा पसंद है');
    assert.strictEqual(sent.length,0); assert.strictEqual(el('learn').checked,false);
    assert.match(el('status').textContent,/Review/); await call('ask()');
    assert.strictEqual(sent.length,1); assert.strictEqual(sent[0].input,'मुझे करुणा पसंद है');
  } else if(scenario==='recognition_lifecycle'){
    call('startListening()'); call('startListening()'); assert.strictEqual(recognizers.length,1);
    el('stop').onclick(); assert.strictEqual(recognizers[0].stopped,1);
    recognizers[0].onresult(result('first')); recognizers[0].onend(); assert.strictEqual(el('listen').disabled,false);
    call('startListening()'); const stale=recognizers[1]; el('language').value='gu-IN'; el('language').onchange();
    assert.strictEqual(stale.aborted,1); stale.onresult(result('should not appear')); assert.strictEqual(el('input').value,'first');
    assert.strictEqual(el('listen').disabled,true); stale.onend();
    startFails=true; call('startListening()'); assert.strictEqual(el('listen').disabled,false); assert.match(el('status').textContent,/Could not start/);
    startFails=false; call('startListening()'); const current=recognizers.at(-1); current.onerror({error:'not-allowed'}); current.onend();
    assert.match(el('status').textContent,/denied/); assert.strictEqual(el('stop').disabled,true);
  } else if(scenario==='stale'){
    let resolve=[]; fetchImpl=()=>new Promise(done=>resolve.push(done)); el('speak-replies').checked=true;
    const first=call('ask()'); await flush(); el('input').value='new question'; const second=call('ask()'); await flush();
    assert.strictEqual(fetched[0].signal.aborted,true);
    resolve[1](reply('new answer')); await second; resolve[0](reply('stale answer')); await first;
    assert.strictEqual(el('answer').textContent,'new answer'); assert.strictEqual(spoken.length,1); assert.strictEqual(spoken[0].text,'new answer');
  } else if(scenario==='cancel'){
    let resolve; fetchImpl=()=>new Promise(done=>resolve=done); const pending=call('ask()'); await flush(); call('stopReply()');
    assert.strictEqual(fetched[0].signal.aborted,true); assert.match(el('status').textContent,/may still finish/);
    resolve(reply('should not appear')); await pending; assert.strictEqual(el('answer').textContent,'Stopped waiting for this reply.');
  } else if(scenario==='speech'){
    await call('ask()'); assert.strictEqual(spoken.length,0);
    el('language').value='gu-IN'; call('readResponse()'); assert.strictEqual(spoken.length,0); assert.match(el('status').textContent,/No matching/);
    voices=[{lang:'gu-IN'}]; call('startListening()'); const microphone=recognizers.at(-1);
    call('readResponse()'); assert.strictEqual(microphone.aborted,1); assert.strictEqual(spoken.length,0);
    microphone.onresult(result('echo must be ignored')); assert.notStrictEqual(el('input').value,'echo must be ignored');
    microphone.onend(); assert.strictEqual(spoken[0].lang,'gu-IN');
    const old=spoken[0]; call('stopReply()'); const status=el('status').textContent; old.onend(); assert.strictEqual(el('status').textContent,status);
    assert.ok(cancelled>0);
  } else if(scenario==='pending_playback_cancel'){
    await call('ask()'); call('startListening()'); const microphone=recognizers.at(-1);
    call('readResponse()'); assert.strictEqual(spoken.length,0);
    microphone.abort=()=>{microphone.aborted++; microphone.onend();}; // Exercise reentrant end dispatch.
    call('stopReply()'); microphone.onend();
    assert.strictEqual(spoken.length,0); assert.strictEqual(el('listen').disabled,false);
  } else if(scenario==='identity_change'){
    let resolve; fetchImpl=()=>new Promise(done=>resolve=done); const pending=call('ask()'); await flush();
    el('user').value='bob'; el('user').oninput(); assert.strictEqual(fetched[0].signal.aborted,true);
    resolve(reply('private Alice response')); await pending; assert.match(el('answer').textContent,/Connection details changed/);
    assert.strictEqual(el('read').disabled,true); assert.strictEqual(el('input').value,''); assert.strictEqual(el('token').value,'');
  } else if(scenario==='destination_change'){
    el('api').value='https://new-destination.invalid'; el('api').oninput();
    assert.strictEqual(el('input').value,''); assert.strictEqual(el('token').value,'');
    el('input').value='new draft'; await call('ask()'); assert.strictEqual(sent.length,0);
    assert.match(el('answer').textContent,/Enter your assigned API token/);
  } else if(scenario==='scope_change'){
    el('memory-scope').value='home'; el('memory-scope').onchange();el('input').value='Home question';checkLearn();
    let resolve; fetchImpl=()=>new Promise(done=>resolve=done); const pending=call('ask()'); await flush();
    assert.strictEqual(sent[0].memory_scope,'home'); assert.strictEqual(sent[0].learn,true);
    el('memory-scope').value='work'; el('memory-scope').oninput();
    assert.strictEqual(fetched[0].signal.aborted,true); assert.strictEqual(el('input').value,'');
    assert.strictEqual(el('token').value,'synthetic-fixture-'+ 'a'.repeat(32)); assert.strictEqual(el('learn').checked,false);
    resolve(reply('old home response','home')); await pending;
    assert.match(el('answer').textContent,/Memory scope changed/); assert.strictEqual(el('read').disabled,true);
    call('startListening()'); const old=recognizers.at(-1);
    el('memory-scope').value='new-scope'; el('memory-scope').oninput();
    old.onresult(result('old work transcript')); old.onend(); assert.strictEqual(el('input').value,'');
    fetchImpl=async()=>reply('new answer'); el('input').value='New scope question'; await call('ask()');
    assert.strictEqual(sent.at(-1).memory_scope,'new-scope'); assert.strictEqual(sent.at(-1).learn,false);
    assert.strictEqual(el('answer').textContent,'new answer');
  } else if(scenario==='scope_validation'){
    for(const scope of ['', 'home\n', 'home\r', 'home\u2028', 'home ']) {
      el('memory-scope').value=scope;el('memory-scope').onchange();el('input').value='Question';await call('ask()'); assert.strictEqual(sent.length,0);
      assert.match(el('answer').textContent,/valid memory scope/);
    }
    el('memory-scope').value='home';el('memory-scope').onchange();el('input').value='Question';fetchImpl=async()=>reply('wrong scope response','work'); await call('ask()');
    assert.match(el('answer').textContent,/did not confirm/); assert.strictEqual(el('read').disabled,true);
    fetchImpl=async()=>response({response:'old API response'}); await call('ask()');
    assert.match(el('answer').textContent,/did not confirm/);
  } else if(scenario==='scope_capability'){
    let resolve; capabilityImpl=()=>new Promise(done=>resolve=done);
    const pending=call('ask()'); assert.strictEqual(sent.length,0);
    el('memory-scope').value='work'; el('memory-scope').oninput();
    resolve(response({memory_scope_protocol:1})); await pending;
    assert.strictEqual(sent.length,0);
    capabilityImpl=async()=>response({status:'ok'});
    el('input').value='A scoped question'; await call('ask()');
    assert.strictEqual(sent.length,0); assert.match(el('answer').textContent,/No question was sent/);
  } else if(scenario==='pagehide'){
    let resolve; fetchImpl=()=>new Promise(done=>resolve=done); const pending=call('ask()'); await flush();
    listeners.pagehide(); assert.strictEqual(fetched[0].signal.aborted,true);
    resolve(reply('late hidden reply')); await pending; assert.notStrictEqual(el('answer').textContent,'late hidden reply');
  } else if(scenario==='unsupported'){
    assert.strictEqual(el('listen').disabled,true); await call('ask()'); assert.strictEqual(el('answer').textContent,'Fixture response');
    call('readResponse()'); assert.match(el('status').textContent,/unavailable/);
  } else throw new Error('unknown scenario');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
