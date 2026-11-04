// Deterministic script harness, not proof of real microphone/browser support.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const scenario = process.argv[2];
const elements = {};
for (const id of ['input','answer','memory-scope','status','meta small','api','token','learn','user','listen','stop','send','cancel','read','language','speak-replies']) {
  elements['#' + id] = {value:'', checked:false, disabled:false, textContent:''};
}
const el = id => elements['#' + id];
el('memory-scope').value='default';
el('input').value='Remember that I prefer quiet rooms';
el('api').value='http://localhost'; el('token').value='synthetic-fixture'; el('user').value='alice'; el('language').value='en-IN';
let sent=[], fetched=[], recognizers=[], voices=[{lang:'en-US'}], spoken=[], cancelled=0, startFails=false;
let fetchImpl=async()=>reply('Fixture response');
let capabilityImpl=async()=>({ok:true,json:async()=>({memory_scope_protocol:1})});
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
function reply(text, scope=el('memory-scope').value){return {ok:true,json:async()=>({memory_scope:scope,response:text,ethical_assessment:{risk_level:'low'},perspectives:[],canonical_evidence:[]})};}
const context=vm.createContext({window,AbortController,document:{querySelector:id=>elements[id]},fetch:(url, request)=>{
  if(request.method==='GET') return capabilityImpl(url,request);
  sent.push(JSON.parse(request.body)); fetched.push(request); return fetchImpl(url,request);
}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/console.js'),'utf8'),context);
const call = code => vm.runInContext(code,context);
const result = text => ({results:[[{transcript:text}]]});
async function run(){
  if(scenario==='consent'){
    el('learn').checked=true; await call('ask()'); await call('ask()');
    assert.strictEqual(sent[0].learn,true); assert.strictEqual(sent[1].learn,false);
    fetchImpl=async()=>{throw new Error('mock failure');}; el('learn').checked=true; await call('ask()');
    fetchImpl=async()=>reply('next'); await call('ask()');
    assert.strictEqual(sent[2].learn,true); assert.strictEqual(sent[3].learn,false);
  } else if(scenario==='transcript'){
    el('language').value='hi-IN'; el('learn').checked=true; call('startListening()');
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
    el('memory-scope').value='home'; el('learn').checked=true;
    let resolve; fetchImpl=()=>new Promise(done=>resolve=done); const pending=call('ask()'); await flush();
    assert.strictEqual(sent[0].memory_scope,'home'); assert.strictEqual(sent[0].learn,true);
    el('memory-scope').value='work'; el('memory-scope').oninput();
    assert.strictEqual(fetched[0].signal.aborted,true); assert.strictEqual(el('input').value,'');
    assert.strictEqual(el('token').value,'synthetic-fixture'); assert.strictEqual(el('learn').checked,false);
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
      el('memory-scope').value=scope; await call('ask()'); assert.strictEqual(sent.length,0);
      assert.match(el('answer').textContent,/valid memory scope/);
    }
    el('memory-scope').value='home'; fetchImpl=async()=>reply('wrong scope response','work'); await call('ask()');
    assert.match(el('answer').textContent,/did not confirm/); assert.strictEqual(el('read').disabled,true);
    fetchImpl=async()=>({ok:true,json:async()=>({response:'old API response'})}); await call('ask()');
    assert.match(el('answer').textContent,/did not confirm/);
  } else if(scenario==='scope_capability'){
    let resolve; capabilityImpl=()=>new Promise(done=>resolve=done);
    const pending=call('ask()'); assert.strictEqual(sent.length,0);
    el('memory-scope').value='work'; el('memory-scope').oninput();
    resolve({ok:true,json:async()=>({memory_scope_protocol:1})}); await pending;
    assert.strictEqual(sent.length,0);
    capabilityImpl=async()=>({ok:true,json:async()=>({status:'ok'})});
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
