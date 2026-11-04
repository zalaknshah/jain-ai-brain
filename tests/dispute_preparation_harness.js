'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=path.join(__dirname,'..'),html=fs.readFileSync(path.join(root,'web/dispute.html'),'utf8');
for(const match of html.matchAll(/<textarea[^>]*>/g))assert.match(match[0],/spellcheck="false"/);
assert.ok(!/<(?:script|link|img)[^>]+(?:src|href)="https?:/i.test(html));
class Element {
 constructor(id){Object.assign(this,{id,value:'',textContent:'',checked:false,hidden:false,disabled:false,children:[],parent:null});}
 append(...children){for(const child of children){if(child&&typeof child==='object')child.parent=this;this.children.push(child);}}
 replaceChildren(...children){this.children=[];this.textContent='';this.append(...children);}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this);}
}
const elements={},events={},calls=[];
for(const match of html.matchAll(/id="([^"]+)"/g)){assert.ok(!elements[match[1]]);elements[match[1]]=new Element(match[1]);}
const scenario=process.argv[2],actual=scenario.startsWith('real_'),token='synthetic-dispute-token-'+'x'.repeat(32);
elements.user.value='alice';elements.token.value=token;elements.api.value=actual?process.env.JACE_TEST_API:'http://127.0.0.1:8787';
if(actual){const url=new URL(elements.api.value);assert.equal(url.protocol,'http:');assert.equal(url.hostname,'127.0.0.1');}
const clone=value=>JSON.parse(JSON.stringify(value));
function report(value){
 const worksheet=clone(value),flagged=Object.values(worksheet.constraints).some(Boolean);
 return {task:'dispute_preparation',protocol:1,status:flagged?'qualified_review_needed':'preparation_only',worksheet,declaration_source:'user_reported',
 partner_position_verified:false,facts_independently_verified:false,constraint_notices:['Declarations are not independent facts.'],clarifying_questions:['What remains unknown?'],
 option_comparisons:worksheet.options.map(option=>({option:clone(option),declaration_source:'user_reported',review_prompts:['Review this declared option without assuming agreement.'],unanswered_questions:clone(option.open_questions)})),
 recommended_option:null,action:null,actions_executed:false,saved:false,provider_called:false,limits:['No verdict, ranking, saving or external action.']};
}
function response(value,status=200,declared=null){
 const bytes=new TextEncoder().encode(JSON.stringify(value));let sent=false;
 return{ok:status>=200&&status<300,status,headers:{get:()=>declared===null?String(bytes.length):declared},body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:async()=>{},releaseLock:()=>{}})}};
}
async function normal(url,options){
 if(url.endsWith('/health'))return response({dispute_preparation_protocol:1});
 assert.ok(url.endsWith('/v1/plans/dispute'));assert.equal(options.method,'POST');
 const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body).sort(),['user_id','worksheet']);assert.equal(body.user_id,'alice');
 return response(report(body.worksheet));
}
let responder=null;
const sandbox={document:{querySelector:q=>{assert.ok(elements[q.slice(1)],q);return elements[q.slice(1)];},createElement:tag=>new Element(tag)},
 window:{addEventListener:(name,fn)=>events[name]=fn},URL,TextEncoder,TextDecoder,Uint8Array,AbortController,
 fetch:async(url,options)=>{calls.push({url,options});return actual?fetch(url,options):(responder?responder(url,options):normal(url,options));}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'web/dispute-preparation.js'),'utf8'),sandbox);
const rows=()=>vm.runInContext('rows',sandbox),click=async id=>elements[id].onclick();
const tick=async()=>{for(let index=0;index<15;index++)await Promise.resolve();};
const deferred=()=>{let resolve;return{promise:new Promise(r=>resolve=r),get resolve(){return resolve;}};};
const postCalls=()=>calls.filter(call=>call.options.method==='POST');
function fill(){
 for(const [id,value] of Object.entries({decision:'Compare a fictional pricing decision.','my-position':'I want more evidence.','partner-position':'They reportedly want to compare options.',
 'facts-agreed':'Both reportedly want a useful result.','facts-disputed':'Whether evidence is sufficient.','facts-unknown':'What a review would require.',
 'risk-safety':'false','risk-deadline':'false','risk-commitment':'false'})){elements[id].value=value;elements[id].oninput();}
 rows().forEach((row,index)=>{for(const [key,value] of Object.entries({label:'Option '+index,description:'An unselected candidate.',my_fit:'yes',reported_partner_fit:'unknown',reversibility:'unknown',agreement:'not_discussed',open_questions:'What remains unclear?'})){row.fields[key].value=value;row.fields[key].oninput();}});
}
async function review(){await click('review');assert.equal(elements['review-panel'].hidden,false);assert.equal(elements.confirm.checked,false);}
async function send(){await review();elements.confirm.checked=true;elements.confirm.onchange();await click('prepare');}
(async()=>{
 assert.equal(calls.length,0);assert.equal(rows().length,2);assert.equal(elements.confirm.checked,false);assert.equal(elements.result.hidden,true);
 if(scenario==='local_review_then_one_send'){
  fill();await review();assert.equal(calls.length,0);assert.match(elements.destination.textContent,/\/v1\/plans\/dispute/);assert.ok(!elements.destination.textContent.includes(token));
  await click('prepare');assert.equal(calls.length,0);elements.confirm.checked=true;const p=click('prepare');assert.equal(elements.confirm.checked,false);await click('prepare');await p;
  assert.equal(calls.length,2);assert.equal(postCalls().length,1);assert.equal(elements.result.hidden,false);assert.equal(elements['review-panel'].hidden,true);
  await click('prepare');assert.equal(postCalls().length,1);assert.equal(elements.comparisons.children.length,2);
  for(const call of calls){assert.equal(call.options.redirect,'error');assert.equal(call.options.credentials,'omit');assert.equal(call.options.cache,'no-store');if(call.url.endsWith('/health'))assert.ok(!call.options.headers.Authorization);}
 } else if(scenario==='editing_and_dynamic_options_invalidate'){
  fill();await review();elements.confirm.checked=true;rows()[0].fields.description.value='Changed option.';rows()[0].fields.description.oninput();
  assert.equal(elements.confirm.checked,false);assert.equal(elements['review-panel'].hidden,true);await click('prepare');assert.equal(calls.length,0);
  await click('add');assert.equal(rows().length,3);await click('add');await click('add');assert.equal(rows().length,4);assert.equal(elements.add.disabled,true);
  rows()[3].remove.onclick();rows()[2].remove.onclick();rows()[0].remove.onclick();assert.equal(rows().length,2);assert.equal(rows()[0].remove.disabled,true);
 } else if(scenario==='invalid_fields_and_destination_before_network'){
  fill();for(const id of ['risk-safety','risk-deadline','risk-commitment']){const old=elements[id].value;elements[id].value='';await click('review');assert.equal(elements['review-panel'].hidden,true);elements[id].value=old;}
  for(const url of ['http://example.com','https://user:secret@example.com','https://example.com/path','https://exa\nmple.com',' https://example.com']){elements.api.value=url;elements.api.oninput();elements.token.value=token;elements.token.oninput();fill();await click('review');assert.equal(elements['review-panel'].hidden,true);}
  elements.api.value='http://127.0.0.1:8787';elements.api.oninput();elements.token.value=token;elements.token.oninput();fill();elements['partner-position'].value='';rows()[0].fields.reported_partner_fit.value='yes';await click('review');assert.equal(elements['review-panel'].hidden,true);
  rows()[0].fields.reported_partner_fit.value='unknown';await review();rows()[1].fields.label.value=rows()[0].fields.label.value;await click('review');assert.equal(elements['review-panel'].hidden,true);assert.equal(calls.length,0);
 } else if(scenario==='silent_changes_before_submit'){
  fill();await review();elements.confirm.checked=true;elements.decision.value='Silent new decision.';await click('prepare');assert.equal(calls.length,0);assert.equal(elements.confirm.checked,false);
  await review();elements.confirm.checked=true;elements.token.value='another-token-'+'z'.repeat(32);await click('prepare');assert.equal(calls.length,0);assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');
 } else if(scenario==='silent_identity_cannot_rebind_existing_draft'){
  for(const stage of ['draft','reviewed','completed']){
   if(stage!=='draft'){elements.user.value='alice';elements.api.value='http://127.0.0.1:8787';elements.token.value=token;elements.token.oninput();}
   fill();if(stage==='reviewed')await review();if(stage==='completed')await send();
   const before=calls.length;elements.api.value='https://another.example';await click('review');
   assert.equal(calls.length,before);assert.equal(elements.decision.value,'');assert.equal(elements.token.value,'');assert.equal(elements.result.hidden,true);assert.equal(elements['review-panel'].hidden,true);
  }
 } else if(scenario==='identity_change_event_clears_private_fields'){
  fill();await review();elements.user.value='bob';elements.user.onchange();assert.equal(elements.decision.value,'');assert.equal(elements.token.value,'');assert.equal(elements['review-panel'].hidden,true);
 } else if(scenario==='silent_identity_during_health'){
  fill();await review();const hold=deferred();responder=()=>hold.promise;elements.confirm.checked=true;const pending=click('prepare');await tick();elements.api.value='https://different.example';
  hold.resolve(response({dispute_preparation_protocol:1}));await pending;assert.equal(calls.length,1);assert.equal(postCalls().length,0);assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');
 } else if(scenario==='silent_draft_during_health'){
  fill();await review();const hold=deferred();responder=()=>hold.promise;elements.confirm.checked=true;const pending=click('prepare');await tick();rows()[0].fields.label.value='Silent different option';
  hold.resolve(response({dispute_preparation_protocol:1}));await pending;assert.equal(postCalls().length,0);assert.equal(elements['review-panel'].hidden,true);assert.equal(elements.confirm.checked,false);
 } else if(scenario==='silent_identity_during_body_stream'){
  fill();const hold=deferred();let cancelled=false;
  responder=(url,options)=>url.endsWith('/health')?normal(url,options):Promise.resolve({ok:true,headers:{get:()=>null},body:{getReader:()=>({read:()=>hold.promise,cancel:async()=>{cancelled=true;},releaseLock:()=>{}})}});
  await review();elements.confirm.checked=true;const pending=click('prepare');await tick();assert.equal(postCalls().length,1);elements.user.value='bob';hold.resolve({done:false,value:new TextEncoder().encode('{}')});await pending;
  assert.equal(cancelled,true);assert.equal(elements.result.hidden,true);assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');
 } else if(scenario==='silent_draft_during_post_suppresses_result'){
  fill();const hold=deferred();responder=(url,options)=>url.endsWith('/health')?normal(url,options):hold.promise;
  await review();elements.confirm.checked=true;const pending=click('prepare');await tick();const sent=JSON.parse(postCalls()[0].options.body).worksheet;
  rows()[0].fields.description.value='Silently changed after submission';hold.resolve(response(report(sent)));await pending;
  assert.equal(elements.result.hidden,true);assert.equal(elements.confirm.checked,false);assert.equal(elements['review-panel'].hidden,true);assert.equal(postCalls().length,1);assert.match(elements.status.textContent,/may already have reached/);
 } else if(scenario==='cancel_late_response_and_no_retry'){
  fill();const hold=deferred();responder=(url,options)=>url.endsWith('/health')?normal(url,options):hold.promise;
  await review();elements.confirm.checked=true;const pending=click('prepare');await tick();const sent=JSON.parse(postCalls()[0].options.body).worksheet;
  await click('cancel');assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');hold.resolve(response(report(sent)));await pending;
  assert.equal(elements.result.hidden,true);await click('prepare');assert.equal(postCalls().length,1);assert.match(elements.status.textContent,/cannot recall/);
 } else if(scenario==='protocol_failure_and_network_failure_no_retry'){
  fill();responder=()=>response({});await send();assert.equal(calls.length,1);assert.equal(postCalls().length,0);assert.equal(elements.confirm.checked,false);
  responder=(url,options)=>url.endsWith('/health')?normal(url,options):Promise.reject(new Error('private server detail'));await send();await click('prepare');assert.equal(postCalls().length,1);assert.ok(!elements.status.textContent.includes('private server detail'));assert.match(elements.status.textContent,/may already have reached/);
 } else if(scenario==='report_binding_and_outcome_flags'){
  fill();const mutations=[data=>data.worksheet.decision='Altered',data=>data.option_comparisons.reverse(),data=>data.option_comparisons[0].unanswered_questions=[],data=>data.declaration_source='verified',data=>data.status='qualified_review_needed',
   ...['saved','provider_called','actions_executed','partner_position_verified','facts_independently_verified'].map(key=>data=>data[key]=true),data=>data.action={},data=>data.recommended_option='Option 0',data=>data.extra='unexpected'];
  for(const mutate of mutations){responder=(url,options)=>{if(url.endsWith('/health'))return normal(url,options);const data=report(JSON.parse(options.body).worksheet);mutate(data);return response(data);};await send();assert.equal(elements.result.hidden,true);assert.equal(elements.confirm.checked,false);}
  assert.equal(postCalls().length,mutations.length);
 } else if(scenario==='text_only_rendering_risk_and_lifecycle_reset'){
  fill();elements.decision.value='<img src=x onerror=alert(1)>';elements['risk-safety'].value='true';
  responder=(url,options)=>{if(url.endsWith('/health'))return normal(url,options);const data=report(JSON.parse(options.body).worksheet);data.option_comparisons[0].review_prompts=['<script>untrusted text</script>'];return response(data);};
  await send();assert.equal(elements.result.hidden,false);assert.match(elements.reported.textContent,/<img/);assert.equal(elements.reported.children.length,0);assert.match(elements.comparisons.children[0].textContent,/<script>/);assert.equal(elements.comparisons.children[0].children.length,0);assert.match(elements['risk-notice'].textContent,/pause ordinary negotiation/);
  events.pagehide();assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');assert.equal(elements.result.hidden,true);
  elements.token.value=token;elements.decision.value='Restored private draft';elements.confirm.checked=true;events.pageshow();assert.equal(elements.token.value,'');assert.equal(elements.decision.value,'');assert.equal(elements.confirm.checked,false);
 } else if(scenario==='oversized_and_invalid_utf8_responses'){
  fill();for(const mode of ['declared','stream','utf8']){
   responder=(url,options)=>{if(url.endsWith('/health'))return normal(url,options);if(mode==='declared')return response({},200,'65537');if(mode==='stream')return response({text:'x'.repeat(65537)},200,'1');let once=false;return {ok:true,headers:{get:()=>null},body:{getReader:()=>({read:async()=>once?{done:true}:(once=true,{done:false,value:new Uint8Array([255])}),cancel:async()=>{},releaseLock:()=>{}})}};};
   await send();assert.equal(elements.result.hidden,true);assert.equal(elements.confirm.checked,false);
  }
  assert.equal(postCalls().length,3);
 } else if(scenario==='real_valid_flags_and_no_persistence'){
  fill();await send();assert.equal(elements.result.hidden,false);assert.equal(elements.comparisons.children.length,2);assert.match(elements.receipt.textContent,/No option is recommended/);
  elements['risk-deadline'].value='true';elements['risk-deadline'].onchange();await send();assert.equal(elements.result.hidden,false);assert.match(elements['risk-notice'].textContent,/does not extend a deadline/);
  assert.equal(postCalls().length,2);
 } else if(scenario==='real_unicode_authoritative_rejection_and_recovery'){
  fill();rows()[0].fields.label.value='Straße';rows()[1].fields.label.value='STRASSE';await send();assert.equal(postCalls().length,1);assert.equal(elements.result.hidden,true);assert.equal(elements.confirm.checked,false);
  rows()[1].fields.label.value='Different candidate';rows()[1].fields.label.oninput();await send();assert.equal(elements.result.hidden,false);assert.equal(postCalls().length,2);
 } else throw new Error('Unknown scenario '+scenario);
 console.log('PASS '+scenario);
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
