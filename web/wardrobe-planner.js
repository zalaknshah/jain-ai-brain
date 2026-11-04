'use strict';
// Explicit local API workflow. No provider, storage, audio or automatic writes.
const element = id => document.querySelector('#' + id);
let generation = 0, pending = null, busy = false, pendingMutation = false;
let selected = null, nextBefore = null, dirty = false;
let boundIdentity = null, activeRaw = null, selectedRaw = null, consentSnapshot = null;
let rows = [], rowSequence = 0;
const CATEGORIES = ['tops', 'bottoms', 'outerwear', 'footwear', 'other'];
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
function formSnapshot() { return JSON.stringify({expires:element('expires').value,minimum:CATEGORIES.map(c => element('minimum-' + c).value),items:rows.map(row => Object.entries(row.fields).map(([key,input]) => [key,input.value]))}); }
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
  for (const id of ['steps', 'limits', 'categories']) element(id).replaceChildren();
}
function markDirty() {
  if (!guardIdentity()) return;
  if (busy) { reset(false); return; }
  consentSnapshot = null; element('confirm').checked = false; dirty = true; clearPlan(); syncControls();
}
function addRow(value = null) {
  if (rows.length >= 30) return;
  const container = document.createElement('fieldset'), legend = document.createElement('legend');
  legend.textContent = 'Item row ' + (++rowSequence); container.append(legend);
  const fields = document.createElement('div'); fields.className = 'row item-fields';
  const row = {container, fields: {}};
  function field(key, title, options = null) {
    const label = document.createElement('label'); label.textContent = title;
    const input = document.createElement(options ? 'select' : 'input');
    if (options) {
      for (const [choice, caption] of [['', 'Choose…'], ...options]) {
        const option = document.createElement('option'); option.value = choice; option.textContent = caption; input.append(option);
      }
    } else {
      input.type = key === 'quantity' ? 'number' : 'text'; input.autocomplete = 'off';
      if (key === 'quantity') { input.min = '1'; input.max = '100'; input.step = '1'; }
      else { input.maxLength = 60; input.spellcheck = false; }
    }
    input.value = value === null ? '' : String(value[key]);
    input.disabled = busy; input.oninput = markDirty; input.onchange = markDirty;
    label.append(input); fields.append(label); row.fields[key] = input;
  }
  const choices = values => values.map(v => [v, v.replaceAll('_', ' ')]);
  field('label', 'Clothing label'); field('category', 'Category', choices(CATEGORIES));
  field('quantity', 'Quantity'); field('condition', 'Condition', choices(['ready', 'repair', 'uncertain']));
  field('fit', 'Fit', choices(['fits', 'does_not_fit', 'uncertain']));
  field('use', 'Current use', choices(['regular', 'occasional', 'unused', 'uncertain']));
  field('preserve', 'Keep / protect from surplus review?', [['true', 'Yes, keep'], ['false', 'No, allow review only']]);
  field('ownership', 'Ownership', [['mine', 'Mine'], ['shared', 'Shared'], ['others', 'Belongs to someone else'], ['uncertain', 'Uncertain']]);
  const remove = document.createElement('button'); remove.textContent = 'Remove this row'; remove.disabled = busy; row.remove = remove;
  remove.onclick = () => {
    if (busy) return;
    rows = rows.filter(r => r !== row); container.remove(); markDirty();
  };
  container.append(fields, remove); rows.push(row); element('items').append(container);
}
function clearForm() {
  selected = null; dirty = false; selectedRaw = null; consentSnapshot = null; rows = []; rowSequence = 0; element('items').replaceChildren(); addRow();
  for (const category of CATEGORIES) element('minimum-' + category).value = '';
  element('expires').value = ''; element('confirm').checked = false;
  element('saved').textContent = 'No saved inventory is selected.';
  element('form-title').textContent = 'New inventory: choose every field';
  element('save').textContent = 'Save new inventory'; clearPlan(); refreshView();
}
function syncControls() {
  for (const id of ['load', 'new', 'save', 'confirm', ...CATEGORIES.map(c => 'minimum-' + c)]) element(id).disabled = busy;
  for (const row of rows) { for (const input of Object.values(row.fields)) input.disabled = busy; row.remove.disabled = busy; }
  element('add').disabled = busy || rows.length >= 30;
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
  clearForm(); nextBefore = null; element('inventories').replaceChildren();
  if (dropToken) element('token').value = '';
  boundIdentity = identitySnapshot();
  syncControls();
  element('status').textContent = uncertain
    ? 'Cleared. A submitted change may have completed. Reload before deciding whether to try again.'
    : 'Cleared. Choose new fields or explicitly load saved inventories when ready.';
}
async function run(work, mutation = false) {
  if (busy || !guardIdentity()) return;
  let ctx;
  try { ctx = context(); } catch (error) { element('status').textContent = error.message; return; }
  const version = ++generation;
  pending = new AbortController(); busy = true; pendingMutation = false; activeRaw = formSnapshot(); clearPlan(); syncControls();
  element('status').textContent = mutation ? 'Checking API before submitting the reviewed inventory…' : 'Loading the requested inventory or checklist…';
  try {
    const health = await request(ctx, version, '/health', {}, false);
    if (health.wardrobe_planner_protocol !== 1 || health.memory_management_protocol !== 1) throw new Error('This API does not support the required wardrobe review protocol.');
    if (!current(version)) return;
    await work(ctx, version);
  } catch (error) {
    if (current(version)) {
      if (pending) pending.abort();
      const uncertain = pendingMutation;
      clearForm(); nextBefore = null; element('inventories').replaceChildren();
      element('status').textContent = error.message + (uncertain ? ' A submitted change may have completed. Reload its state before another action.' : '');
    }
  } finally {
    if (current(version)) { pending = null; busy = false; pendingMutation = false; activeRaw = null; syncControls(); }
  }
}
function exactKeys(value, keys) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}
function whole(value, min, max) { return Number.isSafeInteger(value) && value >= min && value <= max; }
function inventory(value) {
  if (!exactKeys(value, ['items', 'minimum_ready']) || !Array.isArray(value.items) || value.items.length < 1 || value.items.length > 30 ||
      !exactKeys(value.minimum_ready, CATEGORIES) || CATEGORIES.some(c => !whole(value.minimum_ready[c], 0, 50))) throw new Error('Choose every category minimum and include 1–30 complete clothing rows.');
  const seen = new Set(); let total = 0;
  const items = value.items.map(item => {
    if (!exactKeys(item, ['label', 'category', 'quantity', 'condition', 'fit', 'use', 'preserve', 'ownership']) ||
        typeof item.label !== 'string' || item.label !== item.label.trim() || item.label.length < 1 || [...item.label].length > 60 || /\p{C}/u.test(item.label) ||
        !CATEGORIES.includes(item.category) || !whole(item.quantity, 1, 100) || !['ready', 'repair', 'uncertain'].includes(item.condition) ||
        !['fits', 'does_not_fit', 'uncertain'].includes(item.fit) || !['regular', 'occasional', 'unused', 'uncertain'].includes(item.use) ||
        typeof item.preserve !== 'boolean' || !['mine', 'shared', 'others', 'uncertain'].includes(item.ownership)) throw new Error('Every clothing row needs a distinct label and an explicit choice for every field.');
    const label = item.label, key = label.normalize('NFC').toLowerCase();
    if (seen.has(key)) throw new Error('Use a distinct label for every clothing row.');
    seen.add(key); total += item.quantity;
    return Object.freeze({label, category: item.category, quantity: item.quantity, condition: item.condition,
      fit: item.fit, use: item.use, preserve: item.preserve, ownership: item.ownership});
  });
  if (total > 300) throw new Error('Keep the declared inventory at or below 300 total units.');
  const minimum = {}; for (const category of CATEGORIES) minimum[category] = value.minimum_ready[category];
  return Object.freeze({items: Object.freeze(items), minimum_ready: Object.freeze(minimum)});
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
      typeof memory.content !== 'string' || memory.content.length > 65536 ||
      typeof memory.revision !== 'string' || memory.revision !== memory.revision.trim() || !/^[a-f0-9]{64}$/.test(memory.revision) ||
      !(memory.expires_at === null || (typeof memory.expires_at === 'string' && memory.expires_at.length <= 64))) throw new Error('API returned an invalid or mismatched owned memory.');
  normalizedExpiry(memory.expires_at);
  return Object.freeze({...memory});
}
function typedMemory(memory, ctx, id = null) {
  memory = checkedMemory(memory, ctx, id);
  if (memory.source !== 'wardrobe_inventory_v1' || memory.content.length > 10000) throw new Error('Not an eligible typed wardrobe inventory.');
  const data = JSON.parse(memory.content);
  if (!exactKeys(data, ['inventory', 'version']) || data.version !== 1) throw new Error('Invalid stored inventory schema.');
  return Object.freeze({memory, inventory: inventory(data.inventory)});
}
function summary(value) {
  return value.items.map(item => item.label + ': ' + item.quantity + ' ' + item.category + ' • ' + item.condition + ' • ' + item.fit + ' • ' + item.use + ' • ownership ' + item.ownership + ' • keep ' + (item.preserve ? 'yes' : 'no')).join('\n') +
    '\nMinimum ready-to-use needs: ' + CATEGORIES.map(c => c + ' ' + value.minimum_ready[c]).join(', ');
}
function displaySelected(record) {
  selected = record; dirty = false;
  const memory = record.memory, value = record.inventory;
  element('saved').textContent = 'ID ' + memory.memory_id + ' • ' + memory.user_id + ' • scope ' + memory.memory_scope + '\n' + summary(value) + '\nRecall expiry: ' + (memory.expires_at || 'none');
  rows = []; rowSequence = 0; element('items').replaceChildren(); for (const item of value.items) addRow(item);
  for (const c of CATEGORIES) element('minimum-' + c).value = String(value.minimum_ready[c]);
  element('expires').value = memory.expires_at || ''; element('confirm').checked = false;
  element('form-title').textContent = 'Edit selected inventory ' + memory.memory_id + ' (save changes explicitly)';
  element('save').textContent = 'Save changes to selected inventory';
  consentSnapshot = null; selectedRaw = formSnapshot(); refreshView();
}
async function loadPage(before = null) {
  return run(async (ctx, version) => {
    clearForm(); nextBefore = null; element('inventories').replaceChildren();
    const query = '?memory_scope=' + encodeURIComponent(ctx.scope) + '&limit=20' + (before === null ? '' : '&before_id=' + before);
    const page = await request(ctx, version, '/v1/memory/' + encodeURIComponent(ctx.user) + query);
    if (page.memory_scope !== ctx.scope || !Array.isArray(page.memories) || page.memories.length > 20) throw new Error('Invalid memory page.');
    const memories = page.memories.map(m => checkedMemory(m, ctx));
    let previous = before === null ? Number.MAX_SAFE_INTEGER + 1 : before;
    for (const memory of memories) { if (memory.memory_id >= previous) throw new Error('Invalid page order.'); previous = memory.memory_id; }
    if (page.next_before_id !== null && (!Number.isSafeInteger(page.next_before_id) || !memories.length || page.next_before_id !== memories[memories.length - 1].memory_id)) throw new Error('Invalid page cursor.');
    nextBefore = page.next_before_id; let count = 0;
    for (const memory of memories.filter(m => m.source === 'wardrobe_inventory_v1')) {
      const item = document.createElement('li'), note = document.createElement('pre'), button = document.createElement('button');
      note.textContent = 'Inventory ID ' + memory.memory_id + ' • recall expiry: ' + (memory.expires_at || 'none');
      button.textContent = 'Review this inventory'; button.onclick = () => review(memory.memory_id);
      item.append(note, button); element('inventories').append(item); count += 1;
    }
    element('status').textContent = count + ' typed inventory/inventories among ' + memories.length + ' memories on this page. Explicitly review one; none is selected automatically.';
  });
}
async function review(id) {
  if (!Number.isSafeInteger(id) || id < 1) return;
  return run(async (ctx, version) => {
    clearForm(); const result = await request(ctx, version, '/v1/memory-item/' + id);
    displaySelected(typedMemory(result.memory, ctx, id));
    element('status').textContent = 'Fresh saved inventory loaded. Build from these choices, or explicitly confirm an edited replacement. Expiry is rechecked by the API before planning.';
  });
}
function readWhole(input, min, max, label) {
  const text = input.value;
  if (!/^(0|[1-9][0-9]*)$/.test(text) || !whole(Number(text), min, max)) throw new Error('Enter a whole ' + label + ' from ' + min + ' through ' + max + '.');
  return Number(text);
}
async function save() {
  if (busy || !guardIdentity()) return;
  if (!element('confirm').checked) { element('status').textContent = 'Review every choice and select the save confirmation first.'; return; }
  if (!consumeConfirmation()) return;
  let value, submittedExpiry; const expires = element('expires').value;
  try {
    const items = rows.map(row => {
      const value = {}; for (const [key, input] of Object.entries(row.fields)) value[key] = input.value;
      value.quantity = readWhole(row.fields.quantity, 1, 100, 'quantity');
      if (!['true', 'false'].includes(value.preserve)) throw new Error('Explicitly choose whether to keep each item.');
      value.preserve = value.preserve === 'true'; return value;
    });
    const minimum_ready = {};
    for (const c of CATEGORIES) minimum_ready[c] = readWhole(element('minimum-' + c), 0, 50, c + ' minimum');
    value = inventory({items, minimum_ready});
    submittedExpiry = selected ? selected.memory.expires_at : normalizedExpiry(expires || null);
  } catch (error) { element('confirm').checked = false; element('status').textContent = error.message; return; }
  const chosen = selected; element('confirm').checked = false;
  return run(async (ctx, version) => {
    const body = {user_id: ctx.user, inventory: value, confirm_save: true};
    if (chosen) { body.memory_id = chosen.memory.memory_id; body.expected_revision = chosen.memory.revision; }
    else { body.memory_scope = ctx.scope; body.expires_at = expires || null; }
    pendingMutation = true;
    const result = await request(ctx, version, '/v1/wardrobe-inventories', {method: chosen ? 'PATCH' : 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const record = typedMemory(result.memory, ctx, chosen ? chosen.memory.memory_id : null);
    if (JSON.stringify(record.inventory) !== JSON.stringify(value) || (chosen ? record.memory.expires_at !== chosen.memory.expires_at : normalizedExpiry(record.memory.expires_at) !== submittedExpiry)) throw new Error('Saved inventory did not match the reviewed submission.');
    pendingMutation = false; displaySelected(record); nextBefore = null; element('inventories').replaceChildren();
    element('status').textContent = 'API confirmed the saved inventory. Review its displayed choices before building a checklist. No checklist or action was started automatically.';
  }, true);
}
async function plan() {
  if (busy || !guardIdentity() || !selected || dirty) return;
  if (formSnapshot() !== selectedRaw) { markDirty(); element('status').textContent = 'Visible choices changed. Save them explicitly or review the saved record again before planning.'; return; }
  const chosen = selected;
  return run(async (ctx, version) => {
    const body = {user_id: ctx.user, memory_scope: ctx.scope, inventory_memory_id: chosen.memory.memory_id, expected_inventory_revision: chosen.memory.revision};
    const data = await request(ctx, version, '/v1/plans/wardrobe', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    if (data.user_id !== ctx.user || data.memory_scope !== ctx.scope || data.status !== 'planned' || data.action !== null || data.actions_executed !== false) throw new Error('Invalid checklist scope or action status.');
    const record = typedMemory(data.inventory_memory, ctx, chosen.memory.memory_id);
    if (record.memory.revision !== chosen.memory.revision || record.memory.expires_at !== chosen.memory.expires_at || JSON.stringify(inventory(data.inventory_applied)) !== JSON.stringify(chosen.inventory) || JSON.stringify(record.inventory) !== JSON.stringify(chosen.inventory)) throw new Error('Checklist does not match the reviewed inventory.');
    const counts = ['declared_total_units', 'owned_ready_units', 'repair_review_units', 'uncertain_review_units', 'protected_units'];
    if (!exactKeys(data.summary, counts) || counts.some(key => !whole(data.summary[key], 0, 300)) ||
        !Array.isArray(data.categories) || data.categories.length !== 5 ||
        !Array.isArray(data.item_steps) || data.item_steps.length !== chosen.inventory.items.length ||
        !Array.isArray(data.limits) || data.limits.length > 20 || data.limits.some(s => typeof s !== 'string' || s.length > 10000) ||
        typeof data.grounding !== 'string' || data.grounding.length > 20000 || typeof data.context_at !== 'string' || data.context_at.length > 64) throw new Error('Invalid bounded checklist.');
    let declaredTotal = 0, readyTotal = 0, repairTotal = 0, uncertainTotal = 0, protectedTotal = 0;
    const surplus = {};
    for (let i = 0; i < CATEGORIES.length; i++) {
      const category = CATEGORIES[i], result = data.categories[i];
      const ready = chosen.inventory.items.filter(item => item.category === category && item.ownership === 'mine' && item.condition === 'ready' && item.fit === 'fits').reduce((n, item) => n + item.quantity, 0);
      if (!exactKeys(result, ['category', 'minimum_ready', 'owned_ready_units', 'shortfall_units']) || result.category !== category || result.minimum_ready !== chosen.inventory.minimum_ready[category] || result.owned_ready_units !== ready || result.shortfall_units !== Math.max(0, result.minimum_ready - ready)) throw new Error('Category counts do not match the reviewed inventory.');
      readyTotal += ready; surplus[category] = Math.max(0, ready - result.minimum_ready);
    }
    for (let i = 0; i < chosen.inventory.items.length; i++) {
      const item = chosen.inventory.items[i], step = data.item_steps[i]; declaredTotal += item.quantity;
      if (!exactKeys(step, ['label', 'quantity', 'category', 'decision', 'possible_surplus_review_units', 'instruction']) || step.label !== item.label || step.quantity !== item.quantity || step.category !== item.category || !whole(step.possible_surplus_review_units, 0, item.quantity) || typeof step.decision !== 'string' || step.decision.length < 1 || step.decision.length > 100 || typeof step.instruction !== 'string' || step.instruction.length < 1 || step.instruction.length > 10000) throw new Error('Item checklist does not match the reviewed inventory.');
      if (item.ownership === 'mine' && item.condition === 'repair') repairTotal += item.quantity;
      if (item.ownership === 'mine' && (item.condition === 'uncertain' || item.fit !== 'fits' || item.use === 'uncertain')) uncertainTotal += item.quantity;
      if (item.preserve) protectedTotal += item.quantity;
      let decision, reviewUnits = 0;
      if (item.ownership !== 'mine') decision = 'ownership_review';
      else if (item.preserve) decision = 'preserve';
      else if (item.condition === 'repair') decision = 'repair_review';
      else if (item.condition !== 'ready' || item.fit !== 'fits' || item.use === 'uncertain') decision = 'check_fit_or_condition';
      else if (item.use === 'unused' && surplus[item.category] > 0) {
        decision = 'review_possible_surplus'; reviewUnits = Math.min(item.quantity, surplus[item.category]); surplus[item.category] -= reviewUnits;
      } else if (item.use === 'unused') decision = 'keep_for_declared_needs';
      else decision = 'reuse';
      if (step.decision !== decision || step.possible_surplus_review_units !== reviewUnits) throw new Error('Item review eligibility does not match the declared choices.');
    }
    if (data.summary.declared_total_units !== declaredTotal || data.summary.owned_ready_units !== readyTotal || data.summary.repair_review_units !== repairTotal || data.summary.uncertain_review_units !== uncertainTotal || data.summary.protected_units !== protectedTotal) throw new Error('Summary counts do not match the reviewed inventory.');
    element('plan-info').textContent = 'Inventory ' + record.memory.memory_id + ' • scope ' + ctx.scope + '\nContext snapshot: ' + data.context_at + '\nUser-declared units: ' + declaredTotal + '\nOwned, ready and fitting: ' + readyTotal + '\nRepair review: ' + data.summary.repair_review_units + '\nUncertain review: ' + data.summary.uncertain_review_units + '\nProtected: ' + data.summary.protected_units + '\nReview counts overlap; do not add them.';
    for (const category of data.categories) { const li = document.createElement('li'); li.textContent = category.category + ': chosen minimum ' + category.minimum_ready + ', owned ready ' + category.owned_ready_units + ', possible shortfall to review ' + category.shortfall_units; element('categories').append(li); }
    for (const step of data.item_steps) { const li = document.createElement('li'); li.textContent = step.label + ' (' + step.quantity + ' ' + step.category + '): ' + step.instruction; element('steps').append(li); }
    for (const limit of data.limits) { const li = document.createElement('li'); li.textContent = limit; element('limits').append(li); }
    element('grounding').textContent = data.grounding; element('result').hidden = false;
    element('status').textContent = 'Conditional checklist built from the reviewed saved inventory. No actions were performed. Review needs, ownership and uncertainty before any decision.';
  });
}
for (const id of ['user', 'api']) { element(id).oninput = () => reset(true); element(id).onchange = () => reset(true); }
for (const id of ['token', 'scope']) { element(id).oninput = () => reset(false); element(id).onchange = () => reset(false); }
for (const id of ['expires', ...CATEGORIES.map(c => 'minimum-' + c)]) { element(id).oninput = markDirty; element(id).onchange = markDirty; }
element('confirm').onchange = confirmChoices;
element('load').onclick = () => loadPage();
element('older').onclick = () => { if (nextBefore !== null) return loadPage(nextBefore); };
element('new').onclick = () => { if (!busy) { clearForm(); syncControls(); element('status').textContent = 'New blank inventory. Existing saved inventories remain unchanged.'; } };
element('add').onclick = () => { if (!busy && rows.length < 30) { addRow(); markDirty(); } };
element('save').onclick = save; element('plan').onclick = plan; element('cancel').onclick = () => reset(false);
window.addEventListener('pagehide', () => reset(true));
window.addEventListener('pageshow', () => reset(true));
clearForm(); boundIdentity = identitySnapshot(); syncControls();
