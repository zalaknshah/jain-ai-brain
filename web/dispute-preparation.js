'use strict';
// Stateless preparation only. No storage, model, memory, partner contact or retry.
const element = id => document.querySelector('#' + id);
const TOP = ['decision','my-position','partner-position','facts-agreed','facts-disputed','facts-unknown','risk-safety','risk-deadline','risk-commitment'];
const MAX_INPUT_BYTES = 32 * 1024, MAX_RESPONSE_BYTES = 64 * 1024;
let rows = [], sequence = 0, generation = 0, pending = null, busy = false, submitted = false, reviewed = null, boundIdentity = null;
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
const equal = (a,b) => canonical(a) === canonical(b);
const exact = (value,keys) => object(value) && equal(Object.keys(value).sort(), [...keys].sort());
function context() {
  const user = element('user').value, token = element('token').value, rawApi = element('api').value;
  if (!user.trim() || user !== user.trim() || user.length > 200) throw new Error('Enter the exact assigned user ID.');
  if (token.length < 32 || token.length > 4096 || /[^\x21-\x7e]/.test(token)) throw new Error('Enter a valid assigned API token.');
  if (rawApi !== rawApi.trim() || /[\x00-\x20\x7f]/.test(rawApi)) throw new Error('Review the API origin; whitespace is not permitted.');
  let url; try { url = new URL(rawApi); } catch (_) { throw new Error('Enter a valid trusted API origin.'); }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1','[::1]','localhost'].includes(url.hostname)))) throw new Error('Use a trusted HTTPS or local loopback API origin without path, credentials, query or fragment.');
  return Object.freeze({user,token,rawApi,api:url.origin});
}
function rawForm() {
  return canonical({fields:Object.fromEntries(TOP.map(id => [id,element(id).value])),
    options:rows.map(row => Object.fromEntries(Object.entries(row.fields).map(([key,input]) => [key,input.value])))});
}
function identitySnapshot() { return {user:element('user').value,token:element('token').value,rawApi:element('api').value}; }
function sameIdentity(ctx) { return element('user').value === ctx.user && element('token').value === ctx.token && element('api').value === ctx.rawApi; }
function current(version, ctx, raw) {
  if (version !== generation) return false;
  if (!sameIdentity(ctx)) { reset(true); return false; }
  if (rawForm() !== raw) { invalidate(); return false; }
  return true;
}
function clearResult() {
  element('result').hidden = true;
  for (const id of ['receipt','risk-notice','reported']) element(id).textContent = '';
  for (const id of ['notices','questions','comparisons','limits']) element(id).replaceChildren();
}
function clearReview() {
  reviewed = null; element('confirm').checked = false; element('review-panel').hidden = true;
  element('destination').textContent = ''; element('worksheet-preview').textContent = '';
}
function sync() {
  for (const id of TOP) element(id).disabled = busy;
  for (const row of rows) {
    for (const input of Object.values(row.fields)) input.disabled = busy;
    row.remove.disabled = busy || rows.length <= 2;
  }
  element('add').disabled = busy || rows.length >= 4;
  element('review').disabled = busy; element('confirm').disabled = busy || !reviewed;
  element('prepare').disabled = busy || !reviewed || !element('confirm').checked;
}
function invalidate() {
  if (boundIdentity && !sameIdentity(boundIdentity)) { reset(true); return; }
  abandon();
}
function abandon() {
  const wasSent = submitted; generation += 1;
  if (pending) pending.abort(); pending = null; busy = false; submitted = false;
  clearReview(); clearResult(); sync();
  element('status').textContent = wasSent ? 'Review cleared. Details may already have reached the API. No automatic retry; review again before sending.' : 'Choices changed. Review locally again before sending anything.';
}
function addOption() {
  if (rows.length >= 4) return;
  const box = document.createElement('fieldset'), legend = document.createElement('legend');
  legend.textContent = 'Candidate option ' + (++sequence); box.append(legend);
  const row = {box,fields:{}};
  function field(key,caption,choices=null,maximum=null) {
    const label = document.createElement('label'); label.textContent = caption;
    const input = document.createElement(choices ? 'select' : 'textarea');
    input.autocomplete = 'off'; input.spellcheck = false;
    if (choices) for (const [value,text] of [['','Choose…'],...choices]) {
      const option = document.createElement('option'); option.value = value; option.textContent = text; input.append(option);
    }
    if (maximum) input.maxLength = maximum;
    input.value = ''; input.oninput = invalidate; input.onchange = invalidate;
    label.append(input); box.append(label); row.fields[key] = input;
  }
  const choices = [['yes','Yes, as I assess it'],['no','No, as I assess it'],['unknown','Unknown']];
  field('label','Distinct option label, 1–60 characters',null,60);
  field('description','Description, one line and at most 600 characters',null,600);
  field('my_fit','Addresses your reported position?',choices);
  field('reported_partner_fit','Addresses the reported partner position?',choices);
  field('reversibility','Reversible, according to your assessment?',choices);
  field('agreement','Agreement status, as you report it',[['not_discussed','Not discussed'],['reported_agreed','Reported agreed, not verified'],['disputed','Disputed']]);
  field('open_questions','Open questions, one per line, up to five of 400 characters');
  const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove this candidate'; row.remove = remove;
  remove.onclick = () => { if (busy || rows.length <= 2) return; rows = rows.filter(item => item !== row); box.remove(); invalidate(); };
  box.append(remove); rows.push(row); element('options').append(box);
}
function reset(dropToken) {
  abandon();
  for (const id of TOP) element(id).value = '';
  rows = []; sequence = 0; element('options').replaceChildren(); addOption(); addOption();
  if (dropToken) element('token').value = '';
  boundIdentity = identitySnapshot();
  sync(); element('status').textContent = 'Private fields cleared from this page. This cannot recall details already received by the API or surrounding software.';
}
function checkedText(value,name,limit,nullable=false) {
  const result = value.trim();
  if (nullable && result === '') return null;
  if (!result || [...result].length > limit || /[\p{C}\u2028\u2029]/u.test(result)) throw new Error(name + ' must be one trimmed line within its stated character limit, without control or format characters.');
  return result;
}
function lines(value,name,count) {
  const values = value.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
  if (values.length > count) throw new Error(name + ' has too many entries.');
  const result = values.map(item => checkedText(item,name,400));
  if (new Set(result.map(item => item.normalize('NFC').toLowerCase())).size !== result.length) throw new Error(name + ' contains duplicate entries.');
  return result;
}
function worksheet() {
  const decision = checkedText(element('decision').value,'Decision',500);
  const mine = checkedText(element('my-position').value,'Your position',500,true);
  const partner = checkedText(element('partner-position').value,'Reported partner position',500,true);
  const facts = {reported_agreed:lines(element('facts-agreed').value,'Reported agreed facts',8),
    disputed:lines(element('facts-disputed').value,'Disputed claims',8),unknowns:lines(element('facts-unknown').value,'Unknowns',8)};
  const factKeys = Object.values(facts).flat().map(item => item.normalize('NFC').toLowerCase());
  if (new Set(factKeys).size !== factKeys.length) throw new Error('Do not repeat the same fact across status groups.');
  const constraints = {};
  for (const [field,id] of [['safety_concern','risk-safety'],['formal_deadline','risk-deadline'],['binding_commitment','risk-commitment']]) {
    const value = element(id).value;
    if (!['true','false'].includes(value)) throw new Error('Choose every concern flag explicitly.');
    constraints[field] = value === 'true';
  }
  if (rows.length < 2 || rows.length > 4) throw new Error('Enter two to four candidate options.');
  const labels = new Set();
  const options = rows.map(row => {
    const value = Object.fromEntries(Object.entries(row.fields).map(([key,input]) => [key,input.value]));
    const label = checkedText(value.label,'Option label',60), key = label.normalize('NFC').toLowerCase();
    if (labels.has(key)) throw new Error('Use distinct option labels.'); labels.add(key);
    const description = checkedText(value.description,'Option description',600);
    for (const field of ['my_fit','reported_partner_fit','reversibility']) if (!['yes','no','unknown'].includes(value[field])) throw new Error('Choose every option assessment explicitly.');
    if (!['not_discussed','reported_agreed','disputed'].includes(value.agreement)) throw new Error('Choose each option agreement status explicitly.');
    if ((!mine && value.my_fit !== 'unknown') || (!partner && value.reported_partner_fit !== 'unknown')) throw new Error('When a position is blank, its fit must stay unknown.');
    return {label,description,my_fit:value.my_fit,reported_partner_fit:value.reported_partner_fit,reversibility:value.reversibility,agreement:value.agreement,open_questions:lines(value.open_questions,'Option open questions',5)};
  });
  const result = {decision,my_position:mine,partner_position_reported:partner,facts,constraints,options};
  if (new TextEncoder().encode(JSON.stringify(result)).length > MAX_INPUT_BYTES) throw new Error('Worksheet exceeds the 32 KiB local review limit.');
  return result;
}
function review() {
  if (busy) return;
  if (boundIdentity && !sameIdentity(boundIdentity)) { reset(true); return; }
  clearReview(); clearResult();
  try {
    const ctx = context(), value = worksheet(); reviewed = {ctx,value,raw:rawForm()};
    element('destination').textContent = 'User: ' + ctx.user + '\nDestination: ' + ctx.api + '/v1/plans/dispute';
    element('worksheet-preview').textContent = JSON.stringify(value,null,2);
    element('review-panel').hidden = false; element('status').textContent = 'Local review only. No network request has been made. Confirm separately to send this exact worksheet.';
  } catch (error) { element('status').textContent = 'Local review: ' + error.message + ' Nothing was sent.'; }
  sync();
}
async function boundedJSON(response, version, chosen) {
  const declared = response.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_RESPONSE_BYTES)) throw new Error('response limit');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('streaming required');
  const reader = response.body.getReader(), chunks = []; let bytes = 0;
  try {
    while (true) {
      if (!current(version,chosen.ctx,chosen.raw)) throw new Error('stale');
      const part = await reader.read();
      if (!current(version,chosen.ctx,chosen.raw)) throw new Error('stale');
      if (part.done) break;
      if (!(part.value instanceof Uint8Array)) throw new Error('invalid stream');
      bytes += part.value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new Error('response limit'); chunks.push(part.value);
    }
  } catch (error) { try { await reader.cancel(); } catch (_) {} throw error; }
  finally { reader.releaseLock(); }
  const data = new Uint8Array(bytes); let offset = 0;
  for (const chunk of chunks) { data.set(chunk,offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(data));
}
async function request(chosen,version,path,body=null) {
  if (!current(version,chosen.ctx,chosen.raw)) throw new Error('stale');
  const options = {signal:pending.signal,redirect:'error',credentials:'omit',cache:'no-store',headers:{}};
  if (body !== null) { options.method = 'POST'; options.headers = {'Content-Type':'application/json',Authorization:'Bearer ' + chosen.ctx.token}; options.body = JSON.stringify(body); submitted = true; }
  const response = await fetch(chosen.ctx.api + path,options);
  if (!current(version,chosen.ctx,chosen.raw)) throw new Error('stale');
  const data = await boundedJSON(response,version,chosen);
  if (!response.ok) throw new Error('API rejected request');
  return data;
}
function stringList(value,maximum=20) { return Array.isArray(value) && value.length <= maximum && value.every(item => typeof item === 'string' && item.length > 0 && item.length <= 4000 && !/[\p{C}\u2028\u2029]/u.test(item)); }
function checkedReport(data,value) {
  const keys = ['task','protocol','status','worksheet','declaration_source','partner_position_verified','facts_independently_verified','constraint_notices','clarifying_questions','option_comparisons','recommended_option','action','actions_executed','saved','provider_called','limits'];
  const flagged = Object.values(value.constraints).some(Boolean);
  if (!exact(data,keys) || data.task !== 'dispute_preparation' || data.protocol !== 1 || data.status !== (flagged ? 'qualified_review_needed':'preparation_only') ||
      !equal(data.worksheet,value) || data.declaration_source !== 'user_reported' || data.partner_position_verified !== false || data.facts_independently_verified !== false ||
      data.recommended_option !== null || data.action !== null || data.actions_executed !== false || data.saved !== false || data.provider_called !== false ||
      !stringList(data.constraint_notices,3) || data.constraint_notices.length < 1 || !stringList(data.clarifying_questions,5) || !stringList(data.limits,10) || data.limits.length < 1 ||
      !Array.isArray(data.option_comparisons) || data.option_comparisons.length !== value.options.length) throw new Error('report mismatch');
  data.option_comparisons.forEach((item,index) => {
    if (!exact(item,['option','declaration_source','review_prompts','unanswered_questions']) || !equal(item.option,value.options[index]) || item.declaration_source !== 'user_reported' ||
        !equal(item.unanswered_questions,value.options[index].open_questions) || !stringList(item.review_prompts,10) || item.review_prompts.length < 1) throw new Error('option mismatch');
  });
  return data;
}
function appendText(id,text) { const li = document.createElement('li'); li.textContent = text; element(id).append(li); }
function render(data,chosen) {
  element('receipt').textContent = 'Worksheet echo matches the locally reviewed entries. This does not verify their truth or the API’s claims. User: ' + chosen.ctx.user + '. API: ' + chosen.ctx.api + '. No option is recommended.';
  element('risk-notice').textContent = chosen.value.constraints.safety_concern
    ? 'Safety/coercion concern flagged: pause ordinary negotiation or a joint meeting and prioritize a safe setting and appropriate qualified support. No contact or trial is proposed.'
    : Object.values(chosen.value.constraints).some(Boolean) ? 'Deadline or commitment concern flagged: seek appropriate qualified review. This worksheet does not extend a deadline, preserve rights or approve a commitment.'
    : 'No concern was flagged by you. That is not a finding of safety or absence of deadlines or obligations.';
  element('reported').textContent = JSON.stringify(chosen.value,null,2);
  for (const text of data.constraint_notices) appendText('notices',text);
  for (const text of data.clarifying_questions) appendText('questions',text);
  for (const item of data.option_comparisons) appendText('comparisons',item.option.label + '\n' + item.option.description + '\n\nReview prompts:\n' + item.review_prompts.join('\n') + '\n\nYour open questions:\n' + (item.unanswered_questions.join('\n') || 'None entered.'));
  for (const text of data.limits) appendText('limits',text);
  element('result').hidden = false;
}
async function prepare() {
  if (busy || !reviewed) return;
  if (!element('confirm').checked) { element('status').textContent = 'Review and confirm this one worksheet before sending.'; return; }
  element('confirm').checked = false;
  const chosen = reviewed;
  if (!sameIdentity(chosen.ctx)) { reset(true); return; }
  if (rawForm() !== chosen.raw) { invalidate(); return; }
  clearReview(); clearResult(); busy = true; pending = new AbortController(); submitted = false;
  const version = ++generation; sync(); element('status').textContent = 'Confirmation consumed. Checking the API protocol before sending this worksheet…';
  try {
    const health = await request(chosen,version,'/health');
    if (health.dispute_preparation_protocol !== 1) throw new Error('unsupported protocol');
    if (!current(version,chosen.ctx,chosen.raw)) return;
    const data = checkedReport(await request(chosen,version,'/v1/plans/dispute',{user_id:chosen.ctx.user,worksheet:chosen.value}),chosen.value);
    if (!current(version,chosen.ctx,chosen.raw)) return;
    render(data,chosen); element('status').textContent = 'Comparison received for the reviewed worksheet. Reports remain unverified; no option is selected. Review again for any new request.';
  } catch (_) {
    if (current(version,chosen.ctx,chosen.raw)) { clearResult(); element('status').textContent = 'Comparison unavailable or failed validation. Nothing is automatically retried.' + (submitted ? ' Details may already have reached the API. Review again before sending.' : ' Check the API protocol/access, then review again.'); }
  } finally {
    if (version === generation) { if (pending) pending.abort(); pending = null; busy = false; submitted = false; sync(); }
  }
}
for (const id of ['user','api']) { element(id).oninput = () => reset(true); element(id).onchange = () => reset(true); }
element('token').oninput = () => reset(false); element('token').onchange = () => reset(false);
for (const id of TOP) { element(id).oninput = invalidate; element(id).onchange = invalidate; }
element('add').onclick = () => { if (!busy && rows.length < 4) { addOption(); invalidate(); } };
element('review').onclick = review; element('prepare').onclick = prepare; element('confirm').onchange = sync;
element('cancel').onclick = () => reset(true);
window.addEventListener('pagehide', () => reset(true)); window.addEventListener('pageshow', () => reset(true));
clearReview(); clearResult(); addOption(); addOption(); boundIdentity = identitySnapshot(); sync();
