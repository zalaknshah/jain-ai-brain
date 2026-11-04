'use strict';
// Local API client only. No model, browser storage, audio or automatic writes.
const element = id => document.querySelector('#' + id);
let generation = 0;
let pending = null;
let busy = false;
let pendingMutation = false;
let selected = null;
let nextBefore = null;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const controls = ['load', 'older', 'save', 'set-expiry', 'clear-expiry', 'delete', 'content', 'expires', 'confirm-delete', 'confirm-audit'];

function syncControls() {
  for (const id of controls) element(id).disabled = busy;
  element('older').disabled = busy || nextBefore === null;
  const typed = selected && ['cleaning_profile_v1', 'wardrobe_inventory_v1'].includes(selected.memory.source);
  element('save').disabled = busy || !!typed;
  element('content').disabled = busy || !!typed;
}

function clearEditor() {
  selected = null;
  element('editor').hidden = true;
  element('content').value = '';
  element('stored-content').textContent = '';
  element('expires').value = '';
  element('record-info').textContent = '';
  element('expiry-info').textContent = '';
  element('delete-warning').textContent = '';
  element('confirm-delete').checked = false;
  element('confirm-audit').checked = false;
  element('audit-choice').hidden = true;
}

function reset(dropToken = false) {
  generation += 1;
  if (pending) pending.abort();
  const uncertain = pendingMutation;
  pending = null; busy = false; pendingMutation = false;
  clearEditor(); nextBefore = null;
  element('memories').replaceChildren();
  if (dropToken) element('token').value = '';
  syncControls();
  element('status').textContent = uncertain
    ? 'View cleared. A change already sent may have completed. Reload before deciding whether to try again.'
    : 'View cleared. Load memories for the selected account and scope when ready.';
}

function context() {
  const user = element('user').value, scope = element('scope').value, token = element('token').value;
  if (!user.trim() || user.length > 200) throw new Error('Enter the exact assigned user ID.');
  if (scope !== scope.trim() || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(scope)) throw new Error('Enter an exact lowercase memory scope.');
  if (token.length < 32 || token.length > 4096 || /[^\x21-\x7e]/.test(token)) throw new Error('Enter a valid assigned API token.');
  const raw = element('api').value;
  if (raw !== raw.trim()) throw new Error('Review the API address; whitespace is not permitted.');
  const url = new URL(raw);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname)))) {
    throw new Error('Use a trusted HTTPS API origin, or HTTP on a local loopback address. No path, credentials, query or fragment.');
  }
  return Object.freeze({user, scope, token, api: url.origin});
}

function current(version) { return version === generation; }

async function boundedJSON(response) {
  const declared = response.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_RESPONSE_BYTES)) throw new Error('API response exceeds the review limit.');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('This browser needs streaming response support to review private data safely.');
  const reader = response.body.getReader();
  const parts = []; let bytes = 0;
  try {
    while (true) {
      const part = await reader.read();
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
  const data = await boundedJSON(response);
  if (!current(version)) throw new Error('View changed.');
  if (!response.ok) {
    if (response.status === 409) throw new Error('Memory or cleanup requirements changed. Reload and review before trying again.');
    throw new Error('API request failed (' + response.status + '). Review access and reload; no change is automatically retried.');
  }
  return data;
}

async function run(work, mutation = false) {
  if (busy) return;
  let ctx;
  try { ctx = context(); } catch (error) { element('status').textContent = error.message; return; }
  const version = ++generation;
  pending = new AbortController(); busy = true; pendingMutation = mutation; syncControls();
  element('status').textContent = mutation ? 'Submitting the reviewed change…' : 'Loading owned memory records…';
  try {
    const health = await request(ctx, version, '/health', {}, false);
    if (health.memory_management_protocol !== 1) throw new Error('This API does not support the required memory review protocol.');
    if (!current(version)) return;
    await work(ctx, version);
  } catch (error) {
    if (current(version)) {
      if (pending) pending.abort();
      clearEditor(); nextBefore = null; element('memories').replaceChildren();
      element('status').textContent = error.message + (mutation ? ' A submitted change may have completed. Reload its state before another action.' : '');
    }
  } finally {
    if (current(version)) { pending = null; busy = false; pendingMutation = false; syncControls(); }
  }
}

function checkedMemory(memory, ctx, id = null) {
  if (!memory || !Number.isSafeInteger(memory.memory_id) || memory.memory_id < 1 ||
      (id !== null && memory.memory_id !== id) || memory.user_id !== ctx.user || memory.memory_scope !== ctx.scope ||
      typeof memory.content !== 'string' || memory.content.length > 10000 ||
      typeof memory.revision !== 'string' || !/^[a-f0-9]{64}$/.test(memory.revision) || memory.revision !== memory.revision.trim() ||
      !(memory.expires_at === null || (typeof memory.expires_at === 'string' && memory.expires_at.length <= 64))) {
    throw new Error('API returned an invalid or mismatched memory. Nothing is selected.');
  }
  return Object.freeze({...memory});
}

function showEditor(memory, auditCount) {
  selected = Object.freeze({memory, auditCount});
  element('editor').hidden = false;
  element('record-info').textContent = 'Memory ' + memory.memory_id + ' • ' + memory.user_id + ' • scope ' + memory.memory_scope +
    (['cleaning_profile_v1', 'wardrobe_inventory_v1'].includes(memory.source) ? ' • Typed profile or inventory: use its dedicated planner or typed API to edit choices. Expiry and deletion remain available here.' : '');
  element('content').value = memory.content;
  element('stored-content').textContent = memory.content;
  element('expires').value = memory.expires_at || '';
  element('expiry-info').textContent = memory.expires_at ? 'Stored recall expiry: ' + memory.expires_at : 'No recall expiry is set.';
  element('confirm-delete').checked = false; element('confirm-audit').checked = false;
  element('audit-choice').hidden = auditCount === 0;
  element('delete-warning').textContent = auditCount > 0
    ? 'Deleting this item also requires deleting ALL ' + auditCount + ' currently unattributed audit entries for this owner across ALL memory scopes. Other active memories and attributable audits are preserved. Review the separate choice below.'
    : 'Deletes this memory, its graph records and attributable audit entries from the live store. Other active memories stay intact.';
}

async function loadPage(before = null) {
  return run(async (ctx, version) => {
    clearEditor(); nextBefore = null; element('memories').replaceChildren();
    const query = '?memory_scope=' + encodeURIComponent(ctx.scope) + '&limit=20' + (before === null ? '' : '&before_id=' + before);
    const page = await request(ctx, version, '/v1/memory/' + encodeURIComponent(ctx.user) + query);
    if (page.memory_scope !== ctx.scope || !Array.isArray(page.memories) || page.memories.length > 20) throw new Error('Invalid memory page.');
    const memories = page.memories.map(memory => checkedMemory(memory, ctx));
    let previous = before === null ? Number.MAX_SAFE_INTEGER + 1 : before;
    for (const memory of memories) {
      if (memory.memory_id >= previous) throw new Error('Invalid page order.');
      previous = memory.memory_id;
    }
    if (page.next_before_id !== null && (!Number.isSafeInteger(page.next_before_id) ||
        !memories.length || page.next_before_id !== memories[memories.length - 1].memory_id)) throw new Error('Invalid page cursor.');
    nextBefore = page.next_before_id;
    for (const memory of memories) {
      const item = document.createElement('li');
      const text = document.createElement('pre'); text.textContent = memory.content;
      const note = document.createElement('p'); note.textContent = 'ID ' + memory.memory_id + (memory.expires_at ? ' • recall expiry ' + memory.expires_at : ' • no expiry');
      const button = document.createElement('button'); button.textContent = 'Review this item';
      button.onclick = () => review(memory.memory_id);
      item.append(note, text, button); element('memories').append(item);
    }
    element('status').textContent = memories.length + ' saved item(s) on this page, including expired records. Select one to review it freshly.';
  });
}

async function review(id) {
  if (!Number.isSafeInteger(id) || id < 1) return;
  return run(async (ctx, version) => {
    clearEditor();
    const preview = await request(ctx, version, '/v1/memory-item/' + id);
    const memory = checkedMemory(preview.memory, ctx, id);
    if (!Number.isSafeInteger(preview.unattributed_audit_entries) || preview.unattributed_audit_entries < 0 ||
        preview.requires_delete_confirmation !== true ||
        preview.requires_unattributed_audit_cleanup_confirmation !== (preview.unattributed_audit_entries > 0)) throw new Error('Invalid deletion preview.');
    showEditor(memory, preview.unattributed_audit_entries);
    element('status').textContent = 'Fresh record loaded. Changes require an explicit action below; deletion choices are unchecked.';
  });
}

async function change(kind) {
  if (busy || !selected) return;
  const chosen = selected.memory;
  let body = {memory_id: chosen.memory_id, expected_revision: chosen.revision};
  let path = '/v1/memory';
  if (kind === 'content') {
    if (['cleaning_profile_v1', 'wardrobe_inventory_v1'].includes(chosen.source)) { element('status').textContent = 'Use the matching dedicated planner or typed API to edit these choices.'; return; }
    body.content = element('content').value;
    if (!body.content.trim() || body.content.length > 10000) { element('status').textContent = 'Enter reviewed text of 1–10,000 characters.'; return; }
  } else {
    path = '/v1/memory-expiration';
    body.expires_at = kind === 'clear' ? null : element('expires').value;
    if (body.expires_at !== null && (!body.expires_at || body.expires_at.length > 64 || body.expires_at.trim() !== body.expires_at)) {
      element('status').textContent = 'Enter an explicit timezone timestamp, or choose Allow recall without expiration.'; return;
    }
  }
  element('confirm-delete').checked = false; element('confirm-audit').checked = false;
  return run(async (ctx, version) => {
    const result = await request(ctx, version, path, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    checkedMemory(result.memory, ctx, chosen.memory_id);
    clearEditor(); nextBefore = null; element('memories').replaceChildren();
    element('status').textContent = 'Change confirmed by the API. Reload memories to review the current record and any other changes.';
  }, true);
}

async function deleteSelected() {
  if (busy || !selected) return;
  if (!element('confirm-delete').checked || (selected.auditCount > 0 && !element('confirm-audit').checked)) {
    element('status').textContent = 'Review and select each required deletion choice first.'; return;
  }
  const chosen = selected.memory;
  const cleanup = selected.auditCount > 0 && element('confirm-audit').checked;
  element('confirm-delete').checked = false; element('confirm-audit').checked = false;
  return run(async (ctx, version) => {
    const headers = {'X-JACE-Confirm-Delete': String(chosen.memory_id), 'X-JACE-If-Memory-Revision': chosen.revision};
    if (cleanup) headers['X-JACE-Confirm-Audit-Cleanup'] = 'all-unattributed-for-owner';
    const result = await request(ctx, version, '/v1/memory-item/' + chosen.memory_id, {method: 'DELETE', headers});
    if (result.deleted !== 1 || result.memory_id !== chosen.memory_id || result.user_id !== ctx.user) throw new Error('Deletion result did not match the reviewed item.');
    clearEditor(); nextBefore = null; element('memories').replaceChildren();
    element('status').textContent = 'The API confirmed deletion of this item from the live store. Reload to review remaining memories.';
  }, true);
}

for (const id of ['user', 'api']) element(id).oninput = () => reset(true);
for (const id of ['token', 'scope']) element(id).oninput = () => reset(false);
for (const id of ['content', 'expires']) element(id).oninput = () => {
  element('confirm-delete').checked = false; element('confirm-audit').checked = false;
};
element('load').onclick = () => loadPage();
element('older').onclick = () => { if (nextBefore !== null) return loadPage(nextBefore); };
element('save').onclick = () => change('content');
element('set-expiry').onclick = () => change('expiry');
element('clear-expiry').onclick = () => change('clear');
element('delete').onclick = deleteSelected;
element('cancel').onclick = () => reset(false);
window.addEventListener('pagehide', () => reset(true));
syncControls();
