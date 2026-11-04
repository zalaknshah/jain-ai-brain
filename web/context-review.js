'use strict';
// Provider-free preview, explicit selected-only answer, no storage or learning.
const element = id => document.querySelector('#' + id);
const MAX_RESPONSE_BYTES = 64 * 1024;
const HEX = /^[a-f0-9]{64}$/;
let generation = 0, pending = null, busy = false, answerSubmitted = false;
let reviewed = null, choices = [];

function context() {
  const user = element('user').value, scope = element('scope').value, token = element('token').value;
  if (!user.trim() || user.length > 200) throw new Error('Enter the exact assigned user ID.');
  if (scope !== scope.trim() || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(scope)) throw new Error('Enter an exact lowercase memory scope.');
  if (token.length < 32 || token.length > 4096 || /[^\x21-\x7e]/.test(token)) throw new Error('Enter a valid assigned API token.');
  const rawApi = element('api').value, rawInput = element('question').value;
  if (rawApi !== rawApi.trim() || /[\x00-\x20\x7f]/.test(rawApi)) throw new Error('Review the API address; whitespace is not permitted.');
  const url = new URL(rawApi);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname)))) {
    throw new Error('Use a trusted HTTPS API origin, or HTTP on a local loopback address. No path, credentials, query or fragment.');
  }
  const input = rawInput.trim();
  if (!input || rawInput.length > 10000) throw new Error('Enter a question of 1 to 10,000 characters.');
  return Object.freeze({user, scope, token, api: url.origin, rawApi, rawInput, input});
}
function sameContext(ctx) {
  return element('user').value === ctx.user && element('scope').value === ctx.scope &&
    element('token').value === ctx.token && element('api').value === ctx.rawApi && element('question').value === ctx.rawInput;
}
function current(version, ctx) {
  if (version !== generation) return false;
  if (!sameContext(ctx)) {
    const identityChanged = element('user').value !== ctx.user || element('api').value !== ctx.rawApi || element('token').value !== ctx.token;
    reset(identityChanged, identityChanged);
    return false;
  }
  return true;
}
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function text(value, max = 10000) { return typeof value === 'string' && value.length <= max; }
function revision(value) { return typeof value === 'string' && value.length === 64 && HEX.test(value); }
function timestamp(value, nullable = false) {
  if (nullable && value === null) return true;
  if (!text(value, 64) || value.endsWith('-00:00')) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match) return false;
  const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
  const offsetHour = Number(match[9] || 0), offsetMinute = Number(match[10] || 0);
  if (year < 1 || offsetHour > 23 || offsetMinute > 59) return false;
  const wall = new Date(0);
  wall.setUTCFullYear(year, month - 1, day); wall.setUTCHours(hour, minute, second, 0);
  if (wall.getUTCFullYear() !== year || wall.getUTCMonth() !== month - 1 || wall.getUTCDate() !== day ||
      wall.getUTCHours() !== hour || wall.getUTCMinutes() !== minute || wall.getUTCSeconds() !== second) return false;
  const instant = new Date(wall.getTime() - (offsetHour * 60 + offsetMinute) * 60000 * (match[8] === '-' ? -1 : 1));
  return instant.getUTCFullYear() >= 1 && instant.getUTCFullYear() <= 9999;
}
function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function equal(a, b) { return canonical(a) === canonical(b); }
function validEntry(entry) {
  const fields = ['entry_id','title','principle','guidance','source','work','language','edition','location','license','verified','tags'];
  if (!object(entry) || fields.some(k => !(k in entry)) ||
      Object.keys(entry).some(k => !fields.concat(['source_sha256','source_byte_start','source_byte_end']).includes(k)) ||
      !['entry_id','title','principle','guidance','source','language'].every(k => text(entry[k], k === 'principle' ? 20000 : 10000)) || !entry.entry_id ||
      !['work','edition','location','license'].every(k => entry[k] === null || text(entry[k])) ||
      typeof entry.verified !== 'boolean' || !Array.isArray(entry.tags) || entry.tags.length > 100 || entry.tags.some(t => !text(t, 1000))) throw new Error('Invalid source candidate. Refresh the preview.');
  if (['source_sha256','source_byte_start','source_byte_end'].some(k => k in entry) &&
      (!revision(entry.source_sha256) || !Number.isSafeInteger(entry.source_byte_start) || entry.source_byte_start < 0 ||
       !Number.isSafeInteger(entry.source_byte_end) || entry.source_byte_end <= entry.source_byte_start)) throw new Error('Invalid source digest or byte range.');
  return entry;
}
function validMemory(memory, ctx) {
  const fields = ['memory_id','user_id','content','created_at','source','updated_at','expires_at','memory_scope','revision'];
  if (!object(memory) || !equal(Object.keys(memory).sort(), fields.sort()) ||
      !Number.isSafeInteger(memory.memory_id) || memory.memory_id < 1 || memory.user_id !== ctx.user || memory.memory_scope !== ctx.scope ||
      !text(memory.content) || !text(memory.source, 1000) || !revision(memory.revision) || !timestamp(memory.created_at) ||
      !timestamp(memory.updated_at, true) || !timestamp(memory.expires_at, true)) throw new Error('Invalid or mismatched owned memory. Refresh the preview.');
  return memory;
}
function validReasoner(value) {
  if (!object(value) || !equal(Object.keys(value).sort(), ['display_target','kind','revision']) ||
      !['local','http_json','unavailable'].includes(value.kind) || !text(value.display_target, 2560) || !value.display_target || !revision(value.revision)) throw new Error('Invalid configured reasoner descriptor.');
  return value;
}
function validAssessment(value) {
  if (!object(value) || typeof value.allowed !== 'boolean' || !text(value.risk_level, 200) ||
      !Number.isFinite(value.ahimsa_score) || !Number.isFinite(value.aparigraha_score) ||
      !Array.isArray(value.reasons) || value.reasons.length > 50 || value.reasons.some(r => !text(r)) ||
      !(value.safer_alternative === null || text(value.safer_alternative))) throw new Error('Invalid ethical assessment.');
  return value;
}
function checkedPreview(data, ctx) {
  if (!object(data) || data.protocol !== 1 || data.user_id !== ctx.user || data.input !== ctx.input || data.memory_scope !== ctx.scope ||
      !timestamp(data.context_at) || !revision(data.request_revision) || !revision(data.corpus_revision) || typeof data.blocked !== 'boolean' ||
      !Array.isArray(data.canonical_evidence) || data.canonical_evidence.length > 5 || !Array.isArray(data.memories) || data.memories.length > 5 ||
      !Array.isArray(data.limits) || data.limits.length > 50 || data.limits.some(t => !text(t))) throw new Error('Invalid or mismatched context preview.');
  validAssessment(data.ethical_assessment); validReasoner(data.configured_reasoner);
  const sourceIDs = new Set(), memoryIDs = new Set();
  for (const candidate of data.canonical_evidence) {
    if (!object(candidate) || !equal(Object.keys(candidate).sort(), ['entry','revision']) || !revision(candidate.revision)) throw new Error('Invalid source revision.');
    validEntry(candidate.entry);
    if (sourceIDs.has(candidate.entry.entry_id)) throw new Error('Duplicate source candidate.');
    sourceIDs.add(candidate.entry.entry_id);
  }
  for (const memory of data.memories) {
    validMemory(memory, ctx);
    if (memoryIDs.has(memory.memory_id)) throw new Error('Duplicate memory candidate.');
    memoryIDs.add(memory.memory_id);
  }
  if (new TextEncoder().encode(JSON.stringify([data.canonical_evidence, data.memories])).length > 48 * 1024) throw new Error('Context exceeds the review limit.');
  if (data.blocked !== !data.ethical_assessment.allowed || (data.blocked && (sourceIDs.size || memoryIDs.size))) throw new Error('Invalid blocked preview.');
  return data;
}
async function boundedJSON(response) {
  const declared = response.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_RESPONSE_BYTES)) throw new Error('API response exceeds the review limit.');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('Streaming response support is required for private context review.');
  const reader = response.body.getReader(), parts = []; let bytes = 0;
  try {
    while (true) {
      const part = await reader.read(); if (part.done) break;
      bytes += part.value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new Error('API response exceeds the review limit.');
      parts.push(part.value);
    }
  } catch (error) { try { await reader.cancel(); } catch (_) { /* No retry. */ } throw error; }
  finally { reader.releaseLock(); }
  const data = new Uint8Array(bytes); let offset = 0;
  for (const part of parts) { data.set(part, offset); offset += part.byteLength; }
  return JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(data));
}
async function request(ctx, version, path, body = null) {
  if (!current(version, ctx)) throw new Error('View changed.');
  const headers = {}, options = {headers, signal: pending.signal, redirect:'error', credentials:'omit', cache:'no-store'};
  if (body !== null) {
    headers.Authorization = 'Bearer ' + ctx.token; headers['Content-Type'] = 'application/json';
    options.method = 'POST'; options.body = JSON.stringify(body);
  }
  const response = await fetch(ctx.api + path, options);
  if (!current(version, ctx)) throw new Error('View changed.');
  const data = await boundedJSON(response);
  if (!current(version, ctx)) throw new Error('View changed.');
  if (!response.ok) {
    if (response.status === 409) throw new Error('The question, context or configured target changed. Refresh the preview and review again.');
    throw new Error('API request failed (' + response.status + '). Refresh and review; no request is automatically retried.');
  }
  return data;
}
function clearResult() {
  element('result').hidden = true;
  for (const id of ['response','receipt']) element(id).textContent = '';
  for (const id of ['used-sources','used-memories']) element(id).replaceChildren();
}
function clearReview() {
  reviewed = null; choices = []; element('review').hidden = true;
  element('confirm').checked = false; element('mode').value = 'local';
  for (const id of ['review-info','assessment','target','consent-text']) element(id).textContent = '';
  for (const id of ['sources','memories','limits']) element(id).replaceChildren();
}
function syncControls() {
  element('preview').disabled = busy;
  const eligible = reviewed !== null && !reviewed.data.blocked;
  element('mode').disabled = busy || !eligible;
  element('configured-option').disabled = !eligible || reviewed.data.configured_reasoner.kind === 'unavailable';
  element('confirm').disabled = busy || !eligible;
  element('answer').disabled = busy || !eligible || !element('confirm').checked;
  for (const choice of choices) choice.checkbox.disabled = busy || !eligible;
}
function reset(dropToken = false, dropQuestion = false) {
  generation += 1;
  if (pending) pending.abort();
  const uncertain = answerSubmitted;
  pending = null; busy = false; answerSubmitted = false; clearReview(); clearResult();
  if (dropToken) element('token').value = '';
  if (dropQuestion) element('question').value = '';
  syncControls();
  element('status').textContent = uncertain
    ? 'Cleared. The submitted answer request may already have reached the reasoner. It will not be retried. A fresh preview and confirmation are required.'
    : 'Review cleared. Preview again when the question, account and scope are ready.';
}
function sourceText(entry) {
  return 'Source ID: ' + entry.entry_id + '\nTitle: ' + entry.title + '\nPrinciple (full):\n' + entry.principle + '\nGuidance (full):\n' + entry.guidance +
    '\nSource: ' + entry.source + '\nWork: ' + (entry.work ?? 'not supplied') + '\nLanguage: ' + entry.language + '\nEdition: ' + (entry.edition ?? 'not supplied') +
    '\nLocation: ' + (entry.location ?? 'not supplied') + '\nLicense: ' + (entry.license ?? 'not supplied') + '\nHuman review declared in corpus (not independently verified): ' + entry.verified +
    '\nTags: ' + entry.tags.join(', ') + '\nSource SHA-256: ' + (entry.source_sha256 ?? 'not supplied') +
    '\nSource byte range: ' + (entry.source_byte_start === undefined ? 'not supplied' : entry.source_byte_start + ' to ' + entry.source_byte_end + ' (exclusive)');
}
function memoryText(memory) {
  return 'Memory ID: ' + memory.memory_id + '\nOwner: ' + memory.user_id + '\nScope: ' + memory.memory_scope + '\nContent (full):\n' + memory.content +
    '\nSource: ' + memory.source + '\nCreated: ' + memory.created_at + '\nUpdated: ' + (memory.updated_at ?? 'never') +
    '\nRecall expiry: ' + (memory.expires_at ?? 'none') + '\nRevision: ' + memory.revision;
}
function appendText(list, value) { const li = document.createElement('li'); li.textContent = value; element(list).append(li); }
function invalidateConsent() {
  if (busy) { reset(false, false); return; }
  element('confirm').checked = false; clearResult(); updateConsent(); syncControls();
}
function appendChoice(kind, value, description) {
  const li = document.createElement('li'), label = document.createElement('label'), checkbox = document.createElement('input'), note = document.createElement('pre');
  checkbox.type = 'checkbox'; checkbox.checked = false; checkbox.onchange = invalidateConsent;
  label.append(checkbox, document.createTextNode(' Include this ' + (kind === 'source' ? 'source' : 'private memory') + ' for one answer'));
  note.textContent = description; li.append(label, note); element(kind === 'source' ? 'sources' : 'memories').append(li);
  choices.push({kind, value, checkbox});
}
function updateConsent() {
  if (!reviewed) return;
  const descriptor = reviewed.data.configured_reasoner;
  const configured = element('mode').value === 'configured';
  element('target').textContent = 'Configured reasoner: ' + descriptor.kind + '\nTarget: ' + descriptor.display_target + '\nTarget revision: ' + descriptor.revision +
    '\nChosen mode: ' + (configured ? 'configured' : 'local only (configured provider is not used)');
  element('consent-text').textContent = configured
    ? 'I reviewed this question and the checked context. I consent to send the question and only these selected sources and private memories to the configured reasoner shown above for one answer. If it is an HTTP provider, that provider receives this material. Nothing is learned or acted on.'
    : 'I reviewed this question and the checked context. Use the question and only these selected sources and private memories for one local answer. Do not call the configured provider, learn memories or execute actions.';
}
function showPreview(data, ctx) {
  reviewed = {data, ctx};
  element('review-info').textContent = 'Question: ' + data.input + '\nUser: ' + data.user_id + '\nScope: ' + data.memory_scope + '\nContext snapshot: ' + data.context_at +
    '\nRequest revision: ' + data.request_revision + '\nCorpus revision: ' + data.corpus_revision;
  for (const candidate of data.canonical_evidence) appendChoice('source', candidate, sourceText(candidate.entry) + '\nRevision: ' + candidate.revision);
  for (const memory of data.memories) appendChoice('memory', memory, memoryText(memory));
  if (!data.canonical_evidence.length) appendText('sources', 'No source candidates.');
  if (!data.memories.length) appendText('memories', 'No private memory candidates.');
  element('assessment').textContent = JSON.stringify(data.ethical_assessment, null, 2);
  for (const limit of data.limits) appendText('limits', limit);
  element('review').hidden = false; updateConsent();
  element('status').textContent = data.blocked ? 'This question is blocked by the ethical assessment. No context or answer can be selected.'
    : 'Preview ready. Nothing is selected. Review full context, choose a reasoner, and explicitly confirm one answer.';
}
async function run(ctx, work) {
  const version = ++generation;
  pending = new AbortController(); busy = true; answerSubmitted = false; syncControls();
  try {
    const health = await request(ctx, version, '/health');
    if (health.context_review_protocol !== 1) throw new Error('This API does not support the required context review protocol.');
    if (!current(version, ctx)) return;
    await work(version);
  } catch (error) {
    if (current(version, ctx)) {
      if (pending) pending.abort();
      const uncertain = answerSubmitted;
      clearReview(); clearResult();
      element('status').textContent = error.message + (uncertain ? ' The submitted request may already have reached the reasoner. No automatic retry; refresh the preview before any new answer.' : '');
    }
  } finally {
    if (current(version, ctx)) { pending = null; busy = false; answerSubmitted = false; syncControls(); }
  }
}
async function preview() {
  if (busy) return;
  clearReview(); clearResult(); syncControls();
  let ctx; try { ctx = context(); } catch (error) { element('status').textContent = error.message; return; }
  element('status').textContent = 'Retrieving candidates from your API without calling a model or saving a memory…';
  return run(ctx, async version => {
    const data = await request(ctx, version, '/v1/context/preview', {user_id:ctx.user, input:ctx.input, memory_scope:ctx.scope});
    showPreview(checkedPreview(data, ctx), ctx);
  });
}
function checkedAnswer(data, chosen, body, ctx) {
  if (!object(data) || data.user_id !== ctx.user || data.input !== ctx.input || data.memory_scope !== ctx.scope || data.action !== null ||
      !text(data.response, 40000) || !Array.isArray(data.canonical_evidence) || !Array.isArray(data.memories_used)) throw new Error('Answer identity, content or action status did not match the review.');
  const receipt = data.context_review;
  if (!object(receipt) || receipt.protocol !== 1 || receipt.reasoner_mode !== body.reasoner_mode || receipt.request_revision !== body.expected_request_revision ||
      receipt.corpus_revision !== body.expected_corpus_revision || !timestamp(receipt.selected_at) || !equal(receipt.sources, body.sources) || !equal(receipt.memories, body.memories) ||
      !equal(receipt.configured_reasoner, body.reasoner_mode === 'configured' ? chosen.data.configured_reasoner : null)) throw new Error('Answer receipt does not match the selected revisions or configured target.');
  const expectedSources = chosen.sources.map(s => s.entry), expectedMemories = chosen.memories;
  if (!equal(data.canonical_evidence, expectedSources) || !equal(data.memories_used, expectedMemories)) throw new Error('Answer contained missing, extra or changed context. Refresh the preview.');
  validAssessment(data.ethical_assessment);
  if (!data.ethical_assessment.allowed) throw new Error('Answer assessment no longer permits this question. Refresh the preview.');
  return data;
}
async function answer() {
  if (busy || !reviewed || reviewed.data.blocked) return;
  if (!element('confirm').checked) { element('status').textContent = 'Select the explicit one-answer confirmation after reviewing the context.'; return; }
  element('confirm').checked = false; // Consume before validation and before any network request.
  const chosen = {...reviewed, sources:choices.filter(c => c.kind === 'source' && c.checkbox.checked).map(c => c.value),
    memories:choices.filter(c => c.kind === 'memory' && c.checkbox.checked).map(c => c.value)};
  const mode = element('mode').value;
  let ctx;
  try {
    ctx = context();
    if (!sameContext(chosen.ctx)) {
      const identityChanged = element('user').value !== chosen.ctx.user || element('api').value !== chosen.ctx.rawApi || element('token').value !== chosen.ctx.token;
      reset(identityChanged, identityChanged);
      throw new Error('The account, scope or question changed. Refresh the preview.');
    }
    if (!['local','configured'].includes(mode) || (mode === 'configured' && chosen.data.configured_reasoner.kind === 'unavailable')) throw new Error('Review changed or configured reasoner is unavailable. Refresh the preview.');
  } catch (error) { clearReview(); clearResult(); syncControls(); element('status').textContent = error.message; return; }
  const body = {user_id:ctx.user, input:ctx.input, memory_scope:ctx.scope, confirm_context:true, reasoner_mode:mode,
    expected_request_revision:chosen.data.request_revision, expected_corpus_revision:chosen.data.corpus_revision,
    sources:chosen.sources.map(s => ({entry_id:s.entry.entry_id, revision:s.revision})), memories:chosen.memories.map(m => ({memory_id:m.memory_id, revision:m.revision}))};
  if (mode === 'configured') body.expected_reasoner_revision = chosen.data.configured_reasoner.revision;
  clearReview(); clearResult();
  element('status').textContent = 'Confirmation consumed. Checking the API before requesting this one answer…';
  return run(ctx, async version => {
    answerSubmitted = true;
    const data = checkedAnswer(await request(ctx, version, '/v1/context/answer', body), chosen, body, ctx);
    answerSubmitted = false;
    element('response').textContent = data.response;
    element('receipt').textContent = 'Returned context matches the selected records and revisions; semantic support is not verified.\nUser: ' + ctx.user + '\nScope: ' + ctx.scope + '\nQuestion: ' + ctx.input +
      '\nReasoner mode: ' + mode + '\nSelected at: ' + data.context_review.selected_at +
      (mode === 'configured' ? '\nConfigured target: ' + chosen.data.configured_reasoner.display_target : '\nConfigured provider was not used.') +
      '\nRequest revision: ' + data.context_review.request_revision + '\nCorpus revision: ' + data.context_review.corpus_revision;
    for (const source of chosen.sources) appendText('used-sources', sourceText(source.entry) + '\nRevision: ' + source.revision);
    for (const memory of chosen.memories) appendText('used-memories', memoryText(memory));
    if (!chosen.sources.length) appendText('used-sources', 'No sources selected or used.');
    if (!chosen.memories.length) appendText('used-memories', 'No private memories selected or used.');
    element('result').hidden = false;
    element('status').textContent = 'Answer received with matching selected-context receipt. Generated content remains unverified. No learning or actions. Preview again for another answer.';
  });
}
for (const id of ['user','api']) element(id).oninput = () => reset(true, true);
element('token').oninput = () => reset(false, true);
for (const id of ['scope','question']) element(id).oninput = () => reset(false, false);
element('mode').onchange = invalidateConsent;
element('confirm').onchange = syncControls;
element('preview').onclick = preview; element('answer').onclick = answer;
element('cancel').onclick = () => reset(false, true);
window.addEventListener('pagehide', () => reset(true, true));
// Never restore a bfcache/form-restored consent or token.
window.addEventListener('pageshow', () => reset(true, true));
element('confirm').checked = false; element('mode').value = 'local'; syncControls();
