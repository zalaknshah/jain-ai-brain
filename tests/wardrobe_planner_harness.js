'use strict';
const fs = require('fs'), vm = require('vm'), assert = require('assert'), path = require('path');
const root = path.join(__dirname, '..'), html = fs.readFileSync(path.join(root, 'web/wardrobe.html'), 'utf8');
class Element {
  constructor(id) { Object.assign(this, {id, value: '', textContent: '', checked: false, hidden: false, disabled: false, children: [], parent: null}); }
  append(...items) { for (const item of items) { item.parent = this; this.children.push(item); } }
  replaceChildren(...items) { for (const item of this.children) item.parent = null; this.children = []; this.textContent = ''; this.append(...items); }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(item => item !== this); this.parent = null; } }
}
const elements = {}, events = {}, calls = [];
for (const match of html.matchAll(/id="([^"]+)"/g)) { assert.ok(!elements[match[1]]); elements[match[1]] = new Element(match[1]); }
const scenario = process.argv[2], actual = scenario.startsWith('real_');
const token = 'test-alice-' + 'a'.repeat(32);
elements.user.value = 'alice'; elements.scope.value = 'home'; elements.token.value = token;
elements.api.value = actual ? process.env.JACE_TEST_API : 'http://127.0.0.1:8787';
if (actual) { const u = new URL(elements.api.value); assert.equal(u.hostname, '127.0.0.1'); assert.equal(u.protocol, 'http:'); }
const categories = ['tops', 'bottoms', 'outerwear', 'footwear', 'other'];
const baseItem = {label: 'Everyday shirts', category: 'tops', quantity: 5, condition: 'ready', fit: 'fits', use: 'unused', preserve: false, ownership: 'mine'};
const baseInventory = {items: [{...baseItem}], minimum_ready: {tops: 2, bottoms: 0, outerwear: 0, footwear: 0, other: 0}};
let memory = {memory_id: 7, user_id: 'alice', memory_scope: 'home', source: 'wardrobe_inventory_v1', content: JSON.stringify({version: 1, inventory: baseInventory}), revision: 'a'.repeat(64), expires_at: null};
let responder = null;
const response = (data, status = 200, declared = null) => {
  const bytes = new TextEncoder().encode(JSON.stringify(data)); let sent = false;
  return {ok: status >= 200 && status < 300, status, headers: {get: () => declared === null ? String(bytes.length) : declared}, body: {getReader: () => ({read: async () => sent ? {done: true} : (sent = true, {done: false, value: bytes}), cancel: async () => {}, releaseLock: () => {}})}};
};
const planData = () => {
  const inventory = JSON.parse(memory.content).inventory;
  const ready = item => item.ownership === 'mine' && item.condition === 'ready' && item.fit === 'fits';
  const total = check => inventory.items.filter(check).reduce((n, item) => n + item.quantity, 0);
  const counts = Object.fromEntries(categories.map(category => [category, total(item => item.category === category && ready(item))]));
  const surplus = Object.fromEntries(categories.map(category => [category, Math.max(0, counts[category] - inventory.minimum_ready[category])]));
  const steps = inventory.items.map(item => {
    let decision, count = 0;
    if (item.ownership !== 'mine') decision = 'ownership_review';
    else if (item.preserve) decision = 'preserve';
    else if (item.condition === 'repair') decision = 'repair_review';
    else if (item.condition !== 'ready' || item.fit !== 'fits' || item.use === 'uncertain') decision = 'check_fit_or_condition';
    else if (item.use === 'unused' && surplus[item.category] > 0) { decision = 'review_possible_surplus'; count = Math.min(item.quantity, surplus[item.category]); surplus[item.category] -= count; }
    else if (item.use === 'unused') decision = 'keep_for_declared_needs';
    else decision = 'reuse';
    return {label: item.label, category: item.category, quantity: item.quantity, decision, possible_surplus_review_units: count, instruction: 'Review these declared items; no actions performed.'};
  });
  return {user_id: 'alice', memory_scope: 'home', status: 'planned', action: null, actions_executed: false, inventory_memory: {...memory}, inventory_applied: inventory, context_at: '2026-11-04T12:00:00Z',
    summary: {declared_total_units: total(() => true), owned_ready_units: total(ready), repair_review_units: total(item => item.ownership === 'mine' && item.condition === 'repair'), uncertain_review_units: total(item => item.ownership === 'mine' && (item.condition === 'uncertain' || item.fit !== 'fits' || item.use === 'uncertain')), protected_units: total(item => item.preserve)},
    categories: categories.map(category => ({category, minimum_ready: inventory.minimum_ready[category], owned_ready_units: counts[category], shortfall_units: Math.max(0, inventory.minimum_ready[category] - counts[category])})),
    item_steps: steps, grounding: 'Unverified sample summaries, not Agama quotations.', limits: ['Authored conditional checklist; counts overlap.']};
};
async function normal(url, options) {
  const u = new URL(url), method = options.method || 'GET';
  if (u.pathname === '/health') return response({wardrobe_planner_protocol: 1, memory_management_protocol: 1});
  if (u.pathname === '/v1/memory/alice') return response({memory_scope: 'home', memories: [{...memory}], next_before_id: null});
  if (u.pathname === '/v1/memory-item/7') return response({memory: {...memory}, requires_delete_confirmation: true});
  const body = JSON.parse(options.body); assert.equal(body.user_id, 'alice');
  if (u.pathname === '/v1/wardrobe-inventories') {
    assert.equal(body.confirm_save, true);
    if (method === 'PATCH') assert.equal(body.expected_revision, memory.revision);
    else { assert.equal(method, 'POST'); assert.equal(body.memory_scope, 'home'); }
    memory.content = JSON.stringify({version: 1, inventory: body.inventory}); memory.revision = 'b'.repeat(64);
    if (method === 'POST') memory.expires_at = body.expires_at;
    return response({memory: {...memory}}, method === 'POST' ? 201 : 200);
  }
  if (u.pathname === '/v1/plans/wardrobe') { assert.equal(body.inventory_memory_id, memory.memory_id); assert.equal(body.expected_inventory_revision, memory.revision); return response(planData()); }
  throw new Error('Unexpected route ' + method + ' ' + u.pathname);
}
const sandbox = {document: {querySelector: q => { assert.ok(elements[q.slice(1)], q); return elements[q.slice(1)]; }, createElement: t => new Element(t)}, window: {addEventListener: (name, fn) => events[name] = fn}, URL, TextEncoder, TextDecoder, Uint8Array, AbortController,
  fetch: async (url, options) => { calls.push({url, options}); return actual ? fetch(url, options) : (responder ? responder(url, options) : normal(url, options)); }};
vm.createContext(sandbox); vm.runInContext(fs.readFileSync(path.join(root, 'web/wardrobe-planner.js'), 'utf8'), sandbox);
const click = async id => elements[id].onclick();
const tick = async () => { for (let n = 0; n < 20; n++) await Promise.resolve(); };
const deferred = () => { let resolve; return {promise: new Promise(r => resolve = r), get resolve() { return resolve; }}; };
const rows = () => vm.runInContext('rows', sandbox);
const selected = () => vm.runInContext('selected', sandbox);
const writeCalls = () => calls.filter(c => c.url.endsWith('/v1/wardrobe-inventories') && ['POST', 'PATCH'].includes(c.options.method));
const planCalls = () => calls.filter(c => c.url.endsWith('/v1/plans/wardrobe'));
const open = async () => { await click('load'); assert.ok(elements.inventories.children.length, elements.status.textContent); await elements.inventories.children[0].children[1].onclick(); assert.ok(selected(), elements.status.textContent); };
const setField = (key, value, index = 0) => { rows()[index].fields[key].value = String(value); rows()[index].fields[key].oninput(); };
const fillRow = (value = baseItem, index = 0) => { for (const [key, v] of Object.entries(value)) setField(key, v, index); };
const fill = () => { fillRow(); for (const c of categories) { elements['minimum-' + c].value = String(baseInventory.minimum_ready[c]); elements['minimum-' + c].oninput(); } };
const assertBlank = () => { assert.equal(rows().length, 1); for (const input of Object.values(rows()[0].fields)) assert.equal(input.value, ''); for (const c of categories) assert.equal(elements['minimum-' + c].value, ''); assert.equal(elements.confirm.checked, false); assert.equal(elements.result.hidden, true); assert.equal(elements.plan.disabled, true); };
async function actualChange(route, method, body) {
  const result = await fetch(elements.api.value + route, {method, headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  assert.equal(result.status, 200); return result.json();
}
(async () => {
  assert.equal(calls.length, 0); assertBlank();
  assert.ok(!/\b(?:localStorage|sessionStorage|indexedDB|innerHTML)\b/.test(fs.readFileSync(path.join(root, 'web/wardrobe-planner.js'), 'utf8')));
  if (scenario === 'create_review_plan') {
    fill(); await click('save'); assert.equal(calls.length, 0);
    elements.confirm.checked = true; const pending = click('save'); assert.equal(elements.confirm.checked, false); await click('save'); await pending;
    assert.equal(writeCalls().length, 1); assert.equal(planCalls().length, 0); assert.equal(elements.plan.disabled, false);
    await click('plan'); assert.equal(planCalls().length, 1); assert.equal(elements.result.hidden, false); assert.match(elements['plan-info'].textContent, /User-declared/);
    assert.equal(elements.steps.children.length, 1); assert.equal(elements.categories.children.length, 5); assert.equal(elements.confirm.checked, false);
    for (const c of calls) { assert.equal(c.options.redirect, 'error'); assert.equal(c.options.credentials, 'omit'); assert.equal(c.options.cache, 'no-store'); if (c.url.endsWith('/health')) assert.ok(!c.options.headers.Authorization); }
  } else if (scenario === 'edit_and_consumed_consent') {
    await open(); elements.confirm.checked = true; setField('quantity', 6); assert.equal(elements.confirm.checked, false); assert.equal(elements.plan.disabled, true);
    await click('plan'); assert.equal(planCalls().length, 0); await click('save'); assert.equal(writeCalls().length, 0);
    elements.confirm.checked = true; await click('save'); assert.equal(writeCalls().length, 1); assert.equal(writeCalls()[0].options.method, 'PATCH');
    assert.equal(JSON.parse(writeCalls()[0].options.body).expected_revision, 'a'.repeat(64)); assert.equal(elements.expires.disabled, true);
    await click('plan'); assert.match(elements['plan-info'].textContent, /User-declared units: 6/); await click('new'); assertBlank();
  } else if (scenario === 'add_remove_bounds') {
    fill(); elements.confirm.checked = true; await click('add'); assert.equal(rows().length, 2); assert.equal(elements.confirm.checked, false);
    elements.confirm.checked = true; await click('save'); assert.equal(writeCalls().length, 0);
    rows()[1].remove.onclick(); assert.equal(rows().length, 1); assert.equal(elements.items.children.length, 1);
    for (let i = 1; i < 35; i++) await click('add'); assert.equal(rows().length, 30); assert.equal(elements.add.disabled, true);
    rows()[29].remove.onclick(); assert.equal(rows().length, 29); assert.equal(elements.add.disabled, false);
    await click('new'); rows()[0].remove.onclick(); assert.equal(rows().length, 0); elements.confirm.checked = true; await click('save'); assert.equal(writeCalls().length, 0);
  } else if (scenario === 'explicit_paging_selection') {
    responder = (u, o) => u.includes('/v1/memory/alice') ? response({memory_scope: 'home', memories: [{...memory, memory_id: u.includes('before_id') ? 3 : 7}, {...memory, memory_id: u.includes('before_id') ? 2 : 6, source: 'explicit'}], next_before_id: u.includes('before_id') ? null : 6}) : normal(u, o);
    await click('load'); assert.equal(elements.plan.disabled, true); assert.equal(planCalls().length, 0); assert.equal(elements.older.disabled, false); assert.equal(elements.inventories.children.length, 1);
    await click('older'); assert.equal(elements.inventories.children.length, 1); assert.ok(calls.some(c => c.url.includes('before_id=6'))); assert.equal(elements.older.disabled, true);
  } else if (scenario === 'stale_health_boundary') {
    const hold = deferred(); responder = () => hold.promise; fill(); elements.confirm.checked = true; const p = click('save'); await tick();
    elements.api.value = 'https://other.example'; elements.api.oninput(); hold.resolve(response({wardrobe_planner_protocol: 1, memory_management_protocol: 1})); await p;
    assert.equal(calls.length, 1); assert.equal(elements.token.value, ''); assertBlank(); assert.equal(writeCalls().length, 0);
  } else if (scenario === 'stale_body_boundary') {
    const hold = deferred(); responder = (u, o) => u.includes('/v1/memory/alice') ? Promise.resolve({ok: true, headers: {get: () => null}, body: {getReader: () => ({read: () => hold.promise, cancel: async () => {}, releaseLock: () => {}})}}) : normal(u, o);
    const p = click('load'); await tick(); elements.user.value = 'bob'; elements.user.oninput(); hold.resolve({done: true}); await p;
    assert.equal(elements.inventories.children.length, 0); assert.equal(elements.token.value, ''); assertBlank();
  } else if (scenario === 'uncertain_write_no_retry') {
    fill(); const hold = deferred(); responder = (u, o) => u.endsWith('/v1/wardrobe-inventories') ? hold.promise : normal(u, o);
    elements.confirm.checked = true; const p = click('save'); await tick(); assert.equal(writeCalls().length, 1); await click('cancel'); assert.match(elements.status.textContent, /may have completed/);
    hold.resolve(response({memory})); await p; assert.equal(writeCalls().length, 1); assertBlank(); assert.match(elements.status.textContent, /may have completed/);
  } else if (scenario === 'plan_conflict_no_retry') {
    await open(); responder = (u, o) => u.endsWith('/v1/plans/wardrobe') ? response({}, 409) : normal(u, o);
    await click('plan'); await click('plan'); assert.equal(planCalls().length, 1); assertBlank(); assert.match(elements.status.textContent, /Reload/);
  } else if (scenario === 'invalid_inputs_and_protocol') {
    fill(); for (const value of ['', '0', '1.5', '1e1', ' 10', '101', '10\n']) { setField('quantity', value); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); }
    fill(); for (const value of ['', '-1', '1.5', '1e1', ' 10', '51', '10\n']) { elements['minimum-tops'].value = value; elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); }
    fill(); for (const value of ['', 'no', 'FALSE']) { setField('preserve', value); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); }
    fill(); for (const value of ['', ' padded', 'control\nlabel', 'format\u200bhidden']) { setField('label', value); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); }
    fill(); for (const value of ['home\n', 'Home', ' home']) { elements.scope.value = value; elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); }
    elements.scope.value = 'home'; for (const value of ['http://example.com', 'https://user:pass@example.com', 'https://exa\nmple.com', 'https://example.com/path']) { elements.api.value = value; await click('load'); assert.equal(calls.length, 0); }
    elements.api.value = 'http://127.0.0.1:8787'; responder = () => response({memory_management_protocol: 1}); await click('load'); assert.equal(calls.length, 1); assert.match(elements.status.textContent, /protocol/);
  } else if (scenario === 'duplicate_and_total_bounds') {
    fill(); await click('add'); fillRow({...baseItem, label: 'EVERYDAY SHIRTS'}, 1); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0);
    setField('label', 'Café', 0); setField('label', 'Cafe\u0301', 1); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0);
    for (let i = 0; i < 4; i++) { if (rows().length <= i) await click('add'); fillRow({...baseItem, label: 'Item ' + i, quantity: 100}, i); }
    elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0); assert.match(elements.status.textContent, /300/);
  } else if (scenario === 'wrong_scope_and_actions') {
    memory.memory_scope = 'work'; await click('load'); assert.equal(elements.inventories.children.length, 0); memory.memory_scope = 'home';
    for (const change of [data => ({...data, actions_executed: true}), data => ({...data, action: {name: 'dispose'}}), data => ({...data, user_id: 'bob'}), data => ({...data, inventory_memory: {...memory, revision: 'f'.repeat(64)}}), data => ({...data, inventory_applied: {...baseInventory, items: [{...baseItem, quantity: 6}]}})]) {
      responder = null; await open(); responder = (u, o) => u.endsWith('/v1/plans/wardrobe') ? response(change(planData())) : normal(u, o); await click('plan'); assertBlank();
    }
  } else if (scenario === 'mixed_inventory_all_decisions') {
    const variants = [
      {label: 'Shared', ownership: 'shared', preserve: true},
      {label: 'Protected', preserve: true, condition: 'repair', fit: 'uncertain'},
      {label: 'Repair', condition: 'repair'},
      {label: 'Uncertain', condition: 'uncertain'},
      {label: 'Regular', use: 'regular'},
      {label: 'Surplus', quantity: 10},
      {label: 'Keep for need', category: 'bottoms', quantity: 2},
    ];
    const value = {items: variants.map(item => ({...baseItem, ...item})), minimum_ready: {...baseInventory.minimum_ready, tops: 10, bottoms: 2}};
    memory.content = JSON.stringify({version: 1, inventory: value});
    await open(); await click('plan'); assert.equal(elements.result.hidden, false, elements.status.textContent);
    assert.equal(elements.steps.children.length, 7); assert.match(elements['plan-info'].textContent, /Repair review: 10/);
    assert.match(elements['plan-info'].textContent, /Uncertain review: 10/); assert.match(elements['plan-info'].textContent, /Protected: 10/);
    assert.deepEqual(planData().item_steps.map(step => step.decision), ['ownership_review', 'preserve', 'repair_review', 'check_fit_or_condition', 'reuse', 'review_possible_surplus', 'keep_for_declared_needs']);
  } else if (scenario === 'malformed_memory_and_cursor') {
    for (const change of [data => { data.memory_id = Number.MAX_SAFE_INTEGER + 1; }, data => { data.user_id = 'bob'; }, data => { data.revision = 'not-a-revision'; }]) {
      const invalid = {...memory}; change(invalid); responder = (u, o) => u.includes('/v1/memory/alice') ? response({memory_scope: 'home', memories: [invalid], next_before_id: null}) : normal(u, o);
      await click('load'); assertBlank(); assert.equal(elements.inventories.children.length, 0);
    }
    responder = (u, o) => u.includes('/v1/memory/alice') ? response({memory_scope: 'home', memories: [memory], next_before_id: 6}) : normal(u, o);
    await click('load'); assert.match(elements.status.textContent, /cursor/);
    responder = (u, o) => u.includes('/v1/memory-item/') ? response({memory: {...memory, source: 'explicit'}}) : normal(u, o);
    await click('load'); await elements.inventories.children[0].children[1].onclick(); assertBlank(); assert.match(elements.status.textContent, /typed/);
  } else if (scenario === 'token_change_clears_private_draft') {
    await open(); setField('label', 'Private draft'); elements.confirm.checked = true;
    elements.token.value = token + 'x'; elements.token.oninput(); assertBlank(); assert.equal(elements.inventories.children.length, 0); assert.equal(selected(), null);
    assert.equal(elements.saved.textContent, 'No saved inventory is selected.');
  } else if (scenario === 'mismatched_counts_and_surplus') {
    const changes = [data => { data.summary.declared_total_units++; }, data => { data.summary.protected_units++; }, data => { data.categories[0].shortfall_units++; }, data => { data.item_steps[0].possible_surplus_review_units = 4; }, data => { data.item_steps[0].decision = 'dispose'; }, data => { data.item_steps[0].label = 'Other item'; }];
    for (const change of changes) { responder = null; await open(); responder = (u, o) => { if (!u.endsWith('/v1/plans/wardrobe')) return normal(u, o); const data = planData(); change(data); return response(data); }; await click('plan'); assertBlank(); }
  } else if (scenario === 'text_render_and_privacy_reset') {
    await open(); responder = (u, o) => { if (!u.endsWith('/v1/plans/wardrobe')) return normal(u, o); const data = planData(); data.item_steps[0].instruction = '<img src=x onerror=alert(1)>'; data.grounding = '<script>private</script>'; return response(data); };
    await click('plan'); assert.match(elements.steps.children[0].textContent, /<img src=x onerror=alert\(1\)>/); assert.equal(elements.steps.children[0].children.length, 0);
    elements.scope.value = 'work'; elements.scope.oninput(); assert.equal(elements.token.value, token); assertBlank(); assert.equal(elements.grounding.textContent, '');
    fill(); elements.confirm.checked = true; events.pagehide(); assert.equal(elements.token.value, ''); assertBlank();
  } else if (scenario === 'oversized_response') {
    responder = (u, o) => u.endsWith('/health') ? normal(u, o) : response({text: 'x'.repeat(1024 * 1024 + 1)}, 200, '1'); await click('load'); assert.match(elements.status.textContent, /limit/); assert.equal(elements.inventories.children.length, 0);
  } else if (scenario === 'stale_plan_after_cancel') {
    await open(); const hold = deferred(); responder = (u, o) => u.endsWith('/v1/plans/wardrobe') ? hold.promise : normal(u, o); const p = click('plan'); await tick(); await click('cancel'); hold.resolve(response(planData())); await p; assertBlank(); assert.equal(elements.steps.children.length, 0);
  } else if (scenario === 'mismatched_saved_record') {
    fill(); responder = async (u, o) => { const result = await normal(u, o); if (!u.endsWith('/v1/wardrobe-inventories')) return result; memory.user_id = 'bob'; return response({memory}); };
    elements.confirm.checked = true; await click('save'); assertBlank(); assert.match(elements.status.textContent, /may have completed/); assert.equal(writeCalls().length, 1);
  } else if (scenario === 'new_save_expiry_binding') {
    const cases = [
      ['2027-01-01T00:00:00Z', null],
      ['2027-01-01T00:00:00Z', undefined],
      ['2027-01-01T00:00:00Z', '2028-01-01T00:00:00.000000+00:00'],
      ['', '2027-01-01T00:00:00.000000+00:00'],
      ['2027-01-01T00:00:00.123456Z', '2027-01-01T00:00:00.123457+00:00'],
      ['2027-01-01T00:00:00Z', '2027-01-01T00:00:00-00:00'],
      ['2027-01-01T00:00:00Z', '2027-02-29T00:00:00Z'],
    ];
    for (const [submitted, returned] of cases) {
      await click('new'); fill(); elements.expires.value = submitted; elements.expires.oninput();
      responder = async (u, o) => { const result = await normal(u, o); if (!u.endsWith('/v1/wardrobe-inventories')) return result; return response({memory: {...memory, expires_at: returned}}); };
      elements.confirm.checked = true; const before = writeCalls().length; await click('save');
      assertBlank(); assert.match(elements.status.textContent, /may have completed/); assert.equal(writeCalls().length, before + 1);
      await click('save'); assert.equal(writeCalls().length, before + 1); assert.equal(planCalls().length, 0);
    }
  } else if (scenario === 'exact_expiry_normalization') {
    const cases = [
      ['2027-01-01T05:30:00.123456+05:30', '2027-01-01T00:00:00.123456+00:00'],
      ['2026-12-31T19:00:00.000001-05:00', '2027-01-01T00:00:00.000001+00:00'],
      ['2027-01-01T00:00:00Z', '2027-01-01T00:00:00.000000+00:00'],
      ['2027-01-01T00:00:00.1Z', '2027-01-01T00:00:00.100000+00:00'],
      ['2027-01-01T00:00:00.1234Z', '2027-01-01T00:00:00.123400+00:00'],
      ['2027-01-01T00:00:00.12345Z', '2027-01-01T00:00:00.123450+00:00'],
      ['0001-01-01T00:00:00Z', '0001-01-01T00:00:00.000000+00:00'],
      ['2028-02-29T23:30:00.999999-01:00', '2028-03-01T00:30:00.999999+00:00'],
      ['', null],
    ];
    for (const [submitted, returned] of cases) {
      await click('new'); fill(); elements.expires.value = submitted; elements.expires.oninput();
      responder = async (u, o) => { const result = await normal(u, o); if (!u.endsWith('/v1/wardrobe-inventories')) return result; memory.expires_at = returned; return response({memory}); };
      elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /confirmed/, submitted); assert.equal(selected().memory.expires_at, returned);
      assert.equal(JSON.parse(writeCalls().at(-1).options.body).expires_at, submitted || null);
    }
  } else if (scenario === 'invalid_expiry_before_write') {
    fill();
    for (const value of ['2027-01-01T00:00:00-00:00', '2027-02-29T00:00:00Z', '2028-02-30T00:00:00Z', '2027-13-01T00:00:00Z', '2027-00-01T00:00:00Z', '2027-01-00T00:00:00Z', '2027-01-01T24:00:00Z', '2027-01-01T00:60:00Z', '2027-01-01T00:00:60Z', '2027-01-01T00:00:00.1234567Z', '2027-01-01T00:00:00+24:00', '2027-01-01T00:00:00+00:60', '2027-01-01T00:00:00Z\n', '0000-01-01T00:00:00Z', '0001-01-01T00:00:00+00:01', '9999-12-31T23:59:59-00:01', '2027-01-01', 'not-a-dateZ']) {
      elements.expires.value = value; elements.expires.oninput(); elements.confirm.checked = true; await click('save'); assert.equal(calls.length, 0, value); assert.equal(elements.confirm.checked, false);
    }
  } else if (scenario === 'existing_expiry_remains_bound') {
    memory.expires_at = '2027-01-01T00:00:00.000001+00:00'; await open(); setField('quantity', 6);
    responder = async (u, o) => { const result = await normal(u, o); if (!u.endsWith('/v1/wardrobe-inventories')) return result; return response({memory: {...memory, expires_at: '2027-01-01T00:00:00.000002+00:00'}}); };
    elements.confirm.checked = true; await click('save'); assertBlank(); assert.match(elements.status.textContent, /may have completed/); assert.equal(writeCalls()[0].options.method, 'PATCH');
  } else if (scenario === 'multiple_inventory_selection') {
    responder = (u, o) => u.includes('/v1/memory/alice') ? response({memory_scope: 'home', memories: [{...memory, memory_id: 9}, memory], next_before_id: null}) : normal(u, o);
    await click('load'); assert.equal(elements.plan.disabled, true); await elements.inventories.children[1].children[1].onclick(); await click('plan'); assert.equal(JSON.parse(planCalls()[0].options.body).inventory_memory_id, 7);
  } else if (scenario === 'noncanonical_label_preserved') {
    fill(); setField('label', 'Cafe\u0301'); elements.confirm.checked = true; await click('save'); await click('plan'); assert.equal(elements.result.hidden, false); assert.equal(JSON.parse(writeCalls()[0].options.body).inventory.items[0].label, 'Cafe\u0301');
  } else if (scenario === 'real_create_edit_plan') {
    fill(); await click('save'); assert.equal(writeCalls().length, 0); elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /confirmed/); assert.equal(planCalls().length, 0);
    await click('plan'); assert.equal(elements.result.hidden, false, elements.status.textContent); assert.equal(elements.steps.children.length, 1); assert.match(elements.steps.children[0].textContent, /reversible surplus review/);
    await open(); setField('preserve', true); setField('quantity', 6); elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /confirmed/);
    await click('plan'); assert.equal(elements.result.hidden, false, elements.status.textContent); assert.match(elements['plan-info'].textContent, /User-declared units: 6/); assert.match(elements.steps.children[0].textContent, /Preserve/); assert.match(elements.grounding.textContent, /unverified sample/);
  } else if (scenario === 'real_exact_expiry_normalization') {
    fill(); elements.expires.value = '2027-01-01T05:30:00.123456+05:30'; elements.expires.oninput();
    elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /confirmed/);
    assert.equal(selected().memory.expires_at, '2027-01-01T00:00:00.123456+00:00');
    await click('plan'); assert.equal(elements.result.hidden, false, elements.status.textContent);
    setField('quantity', 6); elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /confirmed/);
    assert.equal(selected().memory.expires_at, '2027-01-01T00:00:00.123456+00:00');
  } else if (scenario === 'real_conflict') {
    await open(); const chosen = selected();
    await actualChange('/v1/wardrobe-inventories', 'PATCH', {memory_id: chosen.memory.memory_id, inventory: {...baseInventory, items: [{...baseItem, quantity: 6}]}, expected_revision: chosen.memory.revision, confirm_save: true});
    await click('plan'); assertBlank(); assert.match(elements.status.textContent, /Reload/); assert.equal(planCalls().length, 1);
    await open(); const latest = selected(); await actualChange('/v1/wardrobe-inventories', 'PATCH', {memory_id: latest.memory.memory_id, inventory: {...baseInventory, items: [{...baseItem, quantity: 7}]}, expected_revision: latest.memory.revision, confirm_save: true});
    setField('quantity', 8); elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /Reload/); assert.equal(writeCalls().length, 1);
  } else if (scenario === 'real_expiry_and_isolation') {
    await open(); const chosen = selected(); await actualChange('/v1/memory-expiration', 'PATCH', {memory_id: chosen.memory.memory_id, expires_at: '2000-01-01T00:00:00Z'});
    await click('plan'); assert.match(elements.status.textContent, /404/); assertBlank();
    elements.token.value = 'test-bob-' + 'b'.repeat(32); elements.token.oninput(); fill(); elements.confirm.checked = true; await click('save'); assert.match(elements.status.textContent, /403/);
  } else throw new Error('Unknown scenario ' + scenario);
  console.log('PASS ' + scenario);
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
