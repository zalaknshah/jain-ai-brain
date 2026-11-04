'use strict';
// Explicit local API workflow. No provider, storage, audio or automatic writes.
const element = id => document.querySelector('#' + id);
let generation = 0, pending = null, busy = false, pendingMutation = false;
let selected = null, nextBefore = null, dirty = false;
let boundIdentity = null, activeRaw = null, selectedRaw = null, consentSnapshot = null;
const MAX_RESPONSE_BYTES = 1024 * 1024;
function context() {
  const user = element('user').value, scope = element('scope').value, token = element('token').value;
  if (!user.trim() || user.length > 200) throw new Error('Enter the exact assigned user ID.');
  if (scope !== scope.trim() || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(scope)) throw new Error('Enter an exact lowercase memory scope.');
  if (token.length < 32 || token.length > 4096 || /[^\x21-\x7e]/.test(token)) throw new Error('Enter a valid assigned API token.');
  const raw = element('api').value;
  if (raw !== raw.trim() || /[\x00-\x20\x7f]/.test(raw)) throw new Error('Review the API address; whitespace is not permitted.');
  const url = new URL(raw);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname)))) {
    throw new Error('Use a trusted HTTPS API origin, or HTTP on a local loopback address. No path, credentials, query or fragment.');
  }
  return Object.freeze({user, scope, token, rawApi: raw, api: url.origin});
}

function identitySnapshot() { return {user:element('user').value,scope:element('scope').value,token:element('token').value,rawApi:element('api').value}; }
function sameIdentity(left, right) { return JSON.stringify(left) === JSON.stringify(right); }
function formSnapshot() { return JSON.stringify(['surface','water','minutes','supplies','expires'].map(id => element(id).value)); }
function guardIdentity() {
  const now = identitySnapshot();
  if (boundIdentity && !sameIdentity(now,boundIdentity)) {
    const dropToken = now.user !== boundIdentity.user || now.token !== boundIdentity.token || now.rawApi !== boundIdentity.rawApi;
    reset(dropToken); return false;
  }
  return true;
}
function refreshView() { if (busy) activeRaw = formSnapshot(); }
function current(version) {
  if (version !== generation || !guardIdentity()) return false;
  if (activeRaw !== null && formSnapshot() !== activeRaw) { reset(false); return false; }
  return true;
}
function confirmChoices() {
  if (!guardIdentity()) return;
  consentSnapshot = element('confirm').checked ? {identity:identitySnapshot(),form:formSnapshot()} : null;
}
function consumeConfirmation() {
  const consent = consentSnapshot;
  element('confirm').checked = false; consentSnapshot = null;
  if (!consent || !sameIdentity(consent.identity,identitySnapshot()) || consent.form !== formSnapshot()) {
    dirty = true; clearPlan(); syncControls();
    element('status').textContent = 'Choices or identity changed, or confirmation was restored without a new check. Review and check the save confirmation again.';
    return false;
  }
  return true;
}

async function boundedJSON(response, version) {
  const declared = response.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_RESPONSE_BYTES)) throw new Error('API response exceeds the review limit.');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('This browser needs streaming response support to review private data safely.');
  const reader = response.body.getReader();
  const parts = []; let bytes = 0;
  try {
    while (true) {
      if (!current(version)) throw new Error('View changed.');
      const part = await reader.read();
      if (!current(version)) throw new Error('View changed.');
      if (part.done) break;
      bytes += part.value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new Error('API response exceeds the review limit.');
      parts.push(part.value);
    }
  } catch (error) {
    try { await reader.cancel(); } catch (_) { /* No automatic retry. */ }
    throw error;
  } finally { reader.releaseLock(); }
  const data = new Uint8Array(bytes); let offset = 0;
  for (const part of parts) { data.set(part, offset); offset += part.byteLength; }
  return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(data));
}

async function request(ctx, version, path, options = {}, authorize = true) {
  if (!current(version)) throw new Error('View changed.');
  const headers = {...(options.headers || {})};
  if (authorize) headers.Authorization = 'Bearer ' + ctx.token;
  const response = await fetch(ctx.api + path, {...options, headers, signal: pending.signal,
    redirect: 'error', credentials: 'omit', cache: 'no-store'});
  if (!current(version)) throw new Error('View changed.');
  const data = await boundedJSON(response, version);
  if (!current(version)) throw new Error('View changed.');
  if (!response.ok) {
    if (response.status === 409) throw new Error('Memory or cleanup requirements changed. Reload and review before trying again.');
    throw new Error('API request failed (' + response.status + '). Review access and reload; no change is automatically retried.');
  }
  return data;
}


function clearPlan() {
  element('result').hidden = true;
  for (const id of ['plan-info', 'grounding']) element(id).textContent = '';
  element('steps').replaceChildren(); element('limits').replaceChildren();
}
function clearForm() {
  selected = null; dirty = false; selectedRaw = null; consentSnapshot = null;
  for (const id of ['surface', 'water', 'minutes', 'supplies', 'expires']) element(id).value = '';
  element('confirm').checked = false;
  element('saved').textContent = 'No saved profile is selected.';
  element('form-title').textContent = 'New profile: choose every field';
  element('save').textContent = 'Save new profile'; clearPlan(); refreshView();
}
function syncControls() {
  for (const id of ['load', 'new', 'save', 'surface', 'water', 'minutes', 'supplies', 'confirm']) element(id).disabled = busy;
  element('older').disabled = busy || nextBefore === null;
  element('expires').disabled = busy || selected !== null;
  element('plan').disabled = busy || !selected || dirty;
}
function reset(dropToken = false) {
  // A reset must not rebind a retained credential to a silently changed owner or origin.
  const now = identitySnapshot();
  if (boundIdentity && (now.user !== boundIdentity.user || now.rawApi !== boundIdentity.rawApi)) dropToken = true;
  generation += 1;
  if (pending) pending.abort();
  const uncertain = pendingMutation;
  pending = null; busy = false; pendingMutation = false; activeRaw = null;
  clearForm(); nextBefore = null; element('profiles').replaceChildren();
  if (dropToken) element('token').value = '';
  boundIdentity = identitySnapshot();
  syncControls();
  element('status').textContent = uncertain
    ? 'Cleared. A submitted change may have completed. Reload before deciding whether to try again.'
    : 'Cleared. Choose new fields or explicitly load saved profiles when ready.';
}
async function run(work, mutation = false) {
  if (busy || !guardIdentity()) return;
  let ctx;
  try { ctx = context(); } catch (error) { element('status').textContent = error.message; return; }
  const version = ++generation;
  pending = new AbortController(); busy = true; pendingMutation = false; activeRaw = formSnapshot(); clearPlan(); syncControls();
  element('status').textContent = mutation ? 'Checking API before submitting the reviewed choices…' : 'Loading the requested profile or checklist…';
  try {
    const health = await request(ctx, version, '/health', {}, false);
    if (health.cleaning_planner_protocol !== 1 || health.memory_management_protocol !== 1) throw new Error('This API does not support the required cleaning review protocol.');
    if (!current(version)) return;
    await work(ctx, version);
  } catch (error) {
    if (current(version)) {
      if (pending) pending.abort();
      const uncertain = pendingMutation;
      clearForm(); nextBefore = null; element('profiles').replaceChildren();
      element('status').textContent = error.message + (uncertain ? ' A submitted change may have completed. Reload its state before another action.' : '');
    }
  } finally {
    if (current(version)) { pending = null; busy = false; pendingMutation = false; activeRaw = null; syncControls(); }
  }
}
function profile(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join(',') !== 'supplies_policy,surface,time_budget_minutes,water_policy' ||
      !['wooden_furniture','hard_floor','general'].includes(value.surface) ||
      !['avoid','follow_surface_guidance'].includes(value.water_policy) ||
      !['existing_only','review_missing'].includes(value.supplies_policy) ||
      !Number.isInteger(value.time_budget_minutes) || value.time_budget_minutes < 1 || value.time_budget_minutes > 120) throw new Error('Invalid typed profile. Review the record using the typed API.');
  return Object.freeze({surface:value.surface, water_policy:value.water_policy,
    time_budget_minutes:value.time_budget_minutes, supplies_policy:value.supplies_policy});
}
function normalizedExpiry(value) {
  if (value === null) return null;
  const invalid = () => { throw new Error('Expiry must be a valid timestamp with a known explicit timezone, or blank for no expiry.'); };
  if (typeof value !== 'string' || value !== value.trim() || value.length > 64) return invalid();
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match || value.endsWith('-00:00')) return invalid();
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  const offsetHour = Number(match[10] || 0), offsetMinute = Number(match[11] || 0);
  if (year < 1 || offsetHour > 23 || offsetMinute > 59) return invalid();
  // Dates validate calendar fields and whole-second offsets only. Keep the six
  // fractional digits separately so two instants one microsecond apart differ.
  const wall = new Date(0);
  wall.setUTCFullYear(year, month - 1, day); wall.setUTCHours(hour, minute, second, 0);
  if (wall.getUTCFullYear() !== year || wall.getUTCMonth() !== month - 1 || wall.getUTCDate() !== day ||
      wall.getUTCHours() !== hour || wall.getUTCMinutes() !== minute || wall.getUTCSeconds() !== second) return invalid();
  const offset = (offsetHour * 60 + offsetMinute) * 60000 * (match[9] === '-' ? -1 : 1);
  const utc = new Date(wall.getTime() - offset);
  if (utc.getUTCFullYear() < 1 || utc.getUTCFullYear() > 9999) return invalid();
  return utc.toISOString().slice(0, 19) + '.' + (match[7] || '').padEnd(6, '0') + '+00:00';
}
function checkedMemory(memory, ctx, id = null) {
  if (!memory || !Number.isSafeInteger(memory.memory_id) || memory.memory_id < 1 ||
      (id !== null && memory.memory_id !== id) || memory.user_id !== ctx.user || memory.memory_scope !== ctx.scope ||
      typeof memory.content !== 'string' || memory.content.length > 10000 ||
      typeof memory.revision !== 'string' || memory.revision !== memory.revision.trim() || !/^[a-f0-9]{64}$/.test(memory.revision) ||
      !(memory.expires_at === null || (typeof memory.expires_at === 'string' && memory.expires_at.length <= 64))) throw new Error('API returned an invalid or mismatched owned memory.');
  normalizedExpiry(memory.expires_at);
  return Object.freeze({...memory});
}
function typedMemory(memory, ctx, id = null) {
  memory = checkedMemory(memory, ctx, id);
  if (memory.source !== 'cleaning_profile_v1' || memory.content.length > 2048) throw new Error('Not an eligible typed cleaning profile.');
  const data = JSON.parse(memory.content);
  if (!data || Object.keys(data).sort().join(',') !== 'profile,version' || data.version !== 1) throw new Error('Invalid stored profile schema.');
  return Object.freeze({memory, profile:profile(data.profile)});
}
function summary(p) {
  return 'Surface: ' + p.surface + '\nWater: ' + p.water_policy + '\nTime budget: ' + p.time_budget_minutes + ' minutes\nSupplies: ' + p.supplies_policy;
}
function displaySelected(record) {
  selected = record; dirty = false;
  const m = record.memory, p = record.profile;
  element('saved').textContent = 'ID ' + m.memory_id + ' • ' + m.user_id + ' • scope ' + m.memory_scope + '\n' + summary(p) + '\nRecall expiry: ' + (m.expires_at || 'none');
  element('surface').value=p.surface; element('water').value=p.water_policy;
  element('minutes').value=String(p.time_budget_minutes); element('supplies').value=p.supplies_policy;
  element('expires').value=m.expires_at || ''; element('confirm').checked=false;
  element('form-title').textContent='Edit selected profile ' + m.memory_id + ' (unsaved changes)';
  element('save').textContent='Save changes to selected profile';
  consentSnapshot=null; selectedRaw=formSnapshot(); refreshView();
}
async function loadPage(before = null) {
  return run(async (ctx, version) => {
    clearForm(); nextBefore=null; element('profiles').replaceChildren();
    const query='?memory_scope='+encodeURIComponent(ctx.scope)+'&limit=20'+(before===null?'':'&before_id='+before);
    const page=await request(ctx,version,'/v1/memory/'+encodeURIComponent(ctx.user)+query);
    if(page.memory_scope!==ctx.scope || !Array.isArray(page.memories) || page.memories.length>20) throw new Error('Invalid memory page.');
    const memories=page.memories.map(m=>checkedMemory(m,ctx));
    let previous=before===null?Number.MAX_SAFE_INTEGER+1:before;
    for(const m of memories){if(m.memory_id>=previous)throw new Error('Invalid page order.');previous=m.memory_id;}
    if(page.next_before_id!==null && (!Number.isSafeInteger(page.next_before_id)||!memories.length||page.next_before_id!==memories[memories.length-1].memory_id))throw new Error('Invalid page cursor.');
    nextBefore=page.next_before_id;
    let count=0;
    for(const m of memories.filter(m=>m.source==='cleaning_profile_v1')) {
      const item=document.createElement('li'), note=document.createElement('pre'), button=document.createElement('button');
      note.textContent='Profile ID '+m.memory_id+' • recall expiry: '+(m.expires_at||'none');
      button.textContent='Review this profile';button.onclick=()=>review(m.memory_id);
      item.append(note,button);element('profiles').append(item);count+=1;
    }
    element('status').textContent=count+' typed profile(s) among '+memories.length+' memories on this page. Explicitly review one; no profile is selected automatically.';
  });
}
async function review(id) {
  if(!Number.isSafeInteger(id)||id<1)return;
  return run(async(ctx,version)=>{
    clearForm();const result=await request(ctx,version,'/v1/memory-item/'+id);
    displaySelected(typedMemory(result.memory,ctx,id));
    element('status').textContent='Fresh saved choices loaded. Build from these choices, or explicitly confirm an edited replacement. Expiry is rechecked by the API before planning.';
  });
}
async function save() {
  if(busy || !guardIdentity())return;
  if(!element('confirm').checked){element('status').textContent='Review all choices and select the save confirmation first.';return;}
  if(!consumeConfirmation())return;
  let value, expectedExpiry, expires=element('expires').value;
  try {
    const minutes=element('minutes').value;
    if(!/^[1-9][0-9]{0,2}$/.test(minutes)||minutes!==minutes.trim())throw new Error('Enter a whole time budget from 1 through 120.');
    value=profile({surface:element('surface').value,water_policy:element('water').value,time_budget_minutes:Number(minutes),supplies_policy:element('supplies').value});
    expectedExpiry=normalizedExpiry(selected ? selected.memory.expires_at : expires||null);
  } catch(error){element('confirm').checked=false;element('status').textContent=error.message;return;}
  const chosen=selected;
  element('confirm').checked=false;
  return run(async(ctx,version)=>{
    const body={user_id:ctx.user,profile:value,confirm_save:true};
    if(chosen){body.memory_id=chosen.memory.memory_id;body.expected_revision=chosen.memory.revision;}
    else{body.memory_scope=ctx.scope;body.expires_at=expires||null;}
    pendingMutation=true;
    const result=await request(ctx,version,'/v1/cleaning-profiles',{method:chosen?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const record=typedMemory(result.memory,ctx,chosen?chosen.memory.memory_id:null);
    if(JSON.stringify(record.profile)!==JSON.stringify(value) || normalizedExpiry(record.memory.expires_at)!==expectedExpiry)throw new Error('Saved choices or expiry did not match the reviewed submission.');
    pendingMutation=false;displaySelected(record);nextBefore=null;element('profiles').replaceChildren();
    element('status').textContent='API confirmed the saved profile. Review its displayed choices before building a checklist. No checklist or action was started automatically.';
  },true);
}
async function plan() {
  if(busy || !guardIdentity() || !selected || dirty)return;
  if(formSnapshot()!==selectedRaw){markDirty();element('status').textContent='Visible choices changed. Save them explicitly or review the saved record again before planning.';return;}
  const chosen=selected;
  return run(async(ctx,version)=>{
    const body={user_id:ctx.user,memory_scope:ctx.scope,profile_memory_id:chosen.memory.memory_id,expected_profile_revision:chosen.memory.revision};
    const data=await request(ctx,version,'/v1/plans/cleaning',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(data.user_id!==ctx.user||data.memory_scope!==ctx.scope||data.status!=='planned'||data.action!==null||data.actions_executed!==false)throw new Error('Invalid checklist scope or action status.');
    const record=typedMemory(data.profile_memory,ctx,chosen.memory.memory_id);
    if(record.memory.revision!==chosen.memory.revision||JSON.stringify(profile(data.profile_applied))!==JSON.stringify(chosen.profile)||JSON.stringify(record.profile)!==JSON.stringify(chosen.profile))throw new Error('Checklist does not match the reviewed profile.');
    if(!Array.isArray(data.steps)||!data.steps.length||data.steps.length>20||data.steps.some(s=>!s||typeof s.instruction!=='string'||s.instruction.length>10000)||
       !Array.isArray(data.limits)||data.limits.length>20||data.limits.some(s=>typeof s!=='string'||s.length>10000)||typeof data.grounding!=='string'||data.grounding.length>20000||typeof data.context_at!=='string'||data.context_at.length>64)throw new Error('Invalid bounded checklist.');
    element('plan-info').textContent='Profile '+record.memory.memory_id+' • scope '+ctx.scope+'\nContext snapshot: '+data.context_at+'\n'+summary(chosen.profile);
    for(const step of data.steps){const li=document.createElement('li');li.textContent=step.instruction;element('steps').append(li);}
    for(const limit of data.limits){const li=document.createElement('li');li.textContent=limit;element('limits').append(li);}
    element('grounding').textContent=data.grounding;element('result').hidden=false;
    element('status').textContent='Conditional checklist built from the reviewed saved choices. No actions were performed. Review all checks and evidence qualifications.';
  });
}
function markDirty() {
  if (!guardIdentity()) return;
  if (busy) { reset(false); return; }
  consentSnapshot=null; element('confirm').checked=false; dirty=true; clearPlan(); syncControls();
}
for(const id of ['user','api']){element(id).oninput=()=>reset(true);element(id).onchange=()=>reset(true);}
for(const id of ['token','scope']){element(id).oninput=()=>reset(false);element(id).onchange=()=>reset(false);}
for(const id of ['surface','water','minutes','supplies','expires']){element(id).oninput=markDirty;element(id).onchange=markDirty;}
element('confirm').onchange=confirmChoices;
element('load').onclick=()=>loadPage();
element('older').onclick=()=>{if(nextBefore!==null)return loadPage(nextBefore);};
element('new').onclick=()=>{if(!busy){clearForm();syncControls();element('status').textContent='New blank profile. Existing saved profiles remain unchanged.';}};
element('save').onclick=save;element('plan').onclick=plan;element('cancel').onclick=()=>reset(false);
window.addEventListener('pagehide',()=>reset(true));
window.addEventListener('pageshow',()=>reset(true));
boundIdentity=identitySnapshot();syncControls();
