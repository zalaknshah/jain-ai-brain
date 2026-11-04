'use strict';
// Minimal DOM-script fixtures only. This is not a browser or real-download test.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const scenario = process.argv[2], html = fs.readFileSync(process.argv[3], 'utf8');
const script = [...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)].at(-1)[1];
const embedded = html.match(/<script id="review-snapshot" type="application\/json">([\s\S]*?)<\/script>/)[1];
const original = JSON.parse(embedded), clone = value => JSON.parse(JSON.stringify(value));
class Element {
  constructor(id, env) {
    Object.assign(this, {id, value:'', textContent:'', checked:false, hidden:false, disabled:false, children:[], env});
  }
  append(...values) { this.children.push(...values); }
  set innerHTML(_) { throw new Error('Source data must never become HTML.'); }
  set outerHTML(_) { throw new Error('Source data must never become HTML.'); }
  setAttribute(key, value) { assert.ok(!key.startsWith('on')); this[key] = value; }
  click() {
    assert.equal(this.id, 'a'); this.env.calls.push('click');
    assert.equal(this.env.elements['confirm-save'].checked, false, 'confirmation consumed before click');
    assert.equal(this.env.elements.save.disabled, true);
    this.env.attempts += 1;
    if (this.env.failure === 'click') throw new Error('Synthetic click failure');
    this.env.downloads.push({href:this.href, filename:this.download});
  }
  remove() { this.env.calls.push('remove'); }
}
function setup(data = original, failure = null) {
  const env = {elements:{}, events:{}, calls:[], blobs:[], urls:[], revoked:[], timers:[], downloads:[], attempts:0, failure};
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) {
    assert.ok(!env.elements[match[1]], 'duplicate DOM ID'); env.elements[match[1]] = new Element(match[1], env);
  }
  env.elements['review-snapshot'].textContent = JSON.stringify(data);
  env.elements.review.hidden = true; env.elements.save.disabled = true;
  const document = {
    getElementById:id => { assert.ok(env.elements[id], 'unwired DOM ID: ' + id); return env.elements[id]; },
    createElement:tag => { assert.ok(['li', 'a'].includes(tag), 'unexpected generated element: ' + tag); return new Element(tag, env); },
    body:new Element('body', env)
  };
  const denied = () => { throw new Error('No remote calls, storage, forms, or automatic actions allowed.'); };
  const sandbox = {document, window:{addEventListener:(name, fn) => { assert.ok(['pagehide','pageshow'].includes(name)); env.events[name] = fn; }},
    TextEncoder, Blob:class Blob {
      constructor(parts, options) {
        env.calls.push('blob'); assert.equal(env.elements['confirm-save'].checked, false);
        assert.equal(env.elements.save.disabled, true);
        if (env.failure === 'blob') throw new Error('Synthetic Blob failure');
        assert.equal(parts.length, 1); assert.equal(options.type, 'application/json;charset=utf-8');
        this.text = parts[0]; env.blobs.push(this);
      }
    }, URL:{
      createObjectURL:blob => {
        env.calls.push('createURL'); assert.equal(env.elements['confirm-save'].checked, false);
        if (env.failure === 'url') throw new Error('Synthetic URL failure');
        const url = 'blob:synthetic-' + env.urls.length; env.urls.push({url, blob}); return url;
      },
      revokeObjectURL:url => { env.calls.push('revoke'); env.revoked.push(url); }
    },
    setTimeout:(fn, delay) => { assert.ok(delay <= 1000); env.timers.push(fn); },
    fetch:denied, XMLHttpRequest:denied, WebSocket:denied, alert:denied,
    navigator:{sendBeacon:denied}, location:{assign:denied, replace:denied}
  };
  for (const target of [sandbox, sandbox.window]) {
    for (const key of ['localStorage','sessionStorage','indexedDB']) Object.defineProperty(target, key, {get:denied});
  }
  vm.createContext(sandbox); vm.runInContext(script, sandbox, {timeout:1000});
  env.click = id => { assert.equal(typeof env.elements[id].onclick, 'function', 'unwired control: ' + id); env.elements[id].onclick(); };
  env.input = (id, value) => { env.elements[id].value = value; env.elements[id].oninput(); };
  env.choose = value => { env.elements.decision.value = value; env.elements.decision.onchange(); };
  env.confirm = () => { env.elements['confirm-save'].checked = true; env.elements['confirm-save'].onchange(); };
  env.timersRun = () => { while (env.timers.length) env.timers.shift()(); };
  env.report = () => JSON.parse(env.blobs.at(-1).text);
  return env;
}
function ready(env) { env.input('reviewer', 'Synthetic Reviewer'); env.confirm(); assert.equal(env.elements.save.disabled, false, env.elements.status.textContent); }
function assertNoDownload(env) { assert.equal(env.downloads.length, 0); assert.equal(env.attempts, 0); }
function assertReset(env) {
  assert.equal(env.elements.reviewer.value, ''); assert.equal(env.elements.note.value, '');
  assert.equal(env.elements.decision.value, 'pending'); assert.equal(env.elements['confirm-save'].checked, false);
  assert.equal(env.elements.save.disabled, true); assert.match(env.elements.progress.textContent, /2 pending, 0 approve, 0 reject/);
  assert.equal(env.elements.passage.textContent, original.records[0].entry.principle);
}
if (scenario === 'defaults_navigation') {
  const e = setup(); assertNoDownload(e); assertReset(e);
  assert.equal(e.elements.review.hidden, false); assert.equal(e.elements.previous.disabled, true); assert.equal(e.elements.next.disabled, false);
  assert.equal(e.elements.passage.textContent, original.records[0].entry.principle);
  e.input('note', 'Synthetic approval note.'); e.choose('approve');
  e.click('next'); assert.equal(e.elements.decision.value, 'pending'); assert.equal(e.elements.note.value, '');
  assert.equal(e.elements.passage.textContent, original.records[1].entry.principle);
  e.input('note', 'Synthetic rejection note.'); e.choose('reject'); e.click('previous');
  assert.equal(e.elements.decision.value, 'approve'); assert.equal(e.elements.note.value, 'Synthetic approval note.');
  e.click('next'); assert.equal(e.elements.decision.value, 'reject'); assert.equal(e.elements.note.value, 'Synthetic rejection note.');
  assert.match(e.elements.progress.textContent, /0 pending, 1 approve, 1 reject/);
  e.click('next'); assert.match(e.elements.progress.textContent, /Passage 2 of 2/);
  e.choose('pending'); assert.equal(e.elements.note.value, 'Synthetic rejection note.'); assertNoDownload(e);
} else if (scenario === 'required_fields') {
  const e = setup();
  for (const value of ['', '  ', 'x'.repeat(129), '\ud800', 'bad\u202ename', 'bad\rname']) {
    e.input('reviewer', value); e.confirm(); e.click('save'); assertNoDownload(e); assert.equal(e.elements.save.disabled, true);
  }
  e.input('reviewer', 'Synthetic Reviewer');
  for (const decision of ['approve', 'reject']) {
    e.choose(decision);
    for (const value of ['', '\n \t', 'n'.repeat(2001), '\ud800', 'bad\u0000note', 'bad\rnote']) {
      e.input('note', value); e.confirm(); e.click('save'); assertNoDownload(e);
    }
  }
  e.input('reviewer', 'R'.repeat(128)); e.input('note', 'n'.repeat(2000)); e.confirm(); e.click('save');
  assert.equal(e.downloads.length, 1); assert.equal(e.report().reviewer.length, 128); assert.equal(e.report().decisions[0].note.length, 2000);
  const pending = setup(); pending.input('note', ' \t\r\n'); ready(pending); pending.click('save'); assert.equal(pending.downloads.length, 1);
  const unicode = setup(); unicode.input('reviewer', '🌟'.repeat(128)); unicode.input('note', '🌟'.repeat(2000)); unicode.choose('approve'); unicode.confirm(); unicode.click('save');
  assert.equal(unicode.downloads.length, 1); assert.equal([...unicode.report().decisions[0].note].length, 2000);
} else if (scenario === 'invalid_decisions') {
  for (const decision of ['approved', 'APPROVE', '__proto__', '', null]) {
    const e = setup(); e.input('reviewer', 'Synthetic Reviewer'); e.input('note', 'A note.'); e.choose(decision);
    e.confirm(); e.click('save'); e.click('next'); assertNoDownload(e);
    assert.equal(e.elements.passage.textContent, original.records[0].entry.principle); assert.equal(e.elements['confirm-save'].checked, false);
  }
} else if (scenario === 'report_binding') {
  const pending = setup(); ready(pending); pending.click('save');
  const p = pending.report(); assert.ok(p.decisions.every(value => value.decision === 'pending'));
  assert.deepEqual(Object.keys(p).sort(), ['decisions','draft_revision','format','reviewer']);
  assert.equal(p.format, 'jace-source-decisions-v1'); assert.equal(p.draft_revision, original.draft_revision);
  assert.equal(p.decisions.length, original.records.length);
  for (let i = 0; i < p.decisions.length; i++) {
    assert.deepEqual(Object.keys(p.decisions[i]).sort(), ['decision','entry_id','note','record_revision']);
    assert.equal(p.decisions[i].entry_id, original.records[i].entry.entry_id);
    assert.equal(p.decisions[i].record_revision, original.records[i].revision);
    assert.ok(!pending.blobs[0].text.includes(original.records[i].entry.principle));
  }
  assert.equal(pending.downloads[0].filename, 'jace-source-decisions.json');
  assert.equal(pending.elements['confirm-save'].checked, false); pending.click('save'); assert.equal(pending.downloads.length, 1);
  pending.timersRun(); assert.deepEqual(pending.revoked, [pending.downloads[0].href]);
  const e = setup(); e.input('note', 'approve note'); e.choose('approve'); e.click('next'); e.input('note', 'reject note'); e.choose('reject'); ready(e); e.click('save');
  assert.deepEqual(e.report().decisions.map(d => d.decision), ['approve','reject']);
  assert.deepEqual(e.report().decisions.map(d => d.note), ['approve note','reject note']);
} else if (scenario === 'confirmation_binding') {
  for (const edit of [e => e.input('reviewer', 'Changed Reviewer'), e => e.input('note', 'changed note'), e => e.choose('reject')]) {
    const e = setup(); e.input('note', 'existing note'); ready(e); edit(e);
    assert.equal(e.elements['confirm-save'].checked, false); e.click('save'); assertNoDownload(e);
  }
  for (const [id, value] of [['reviewer','Silent reviewer'], ['note','silent note'], ['decision','approve']]) {
    const e = setup(); e.input('note', 'existing note'); ready(e); e.elements[id].value = value;
    e.click('save'); assertNoDownload(e); assert.equal(e.elements['confirm-save'].checked, false);
  }
  const e = setup(); ready(e); e.click('next'); e.click('previous'); e.click('save'); assert.equal(e.downloads.length, 1, 'navigation alone leaves report content unchanged');
  const blank = setup(); blank.elements['confirm-save'].checked = true; blank.click('save'); assertNoDownload(blank);
} else if (scenario === 'download_failures') {
  for (const stage of ['blob', 'url', 'click']) {
    const e = setup(original, stage); ready(e); e.click('save');
    assert.equal(e.elements['confirm-save'].checked, false); assert.equal(e.elements.save.disabled, true);
    const count = e.calls.length; e.click('save'); assert.equal(e.calls.length, count);
    assert.equal(e.downloads.length, 0); assert.match(e.elements.status.textContent, /Confirm/);
    e.timersRun(); if (stage === 'click') assert.equal(e.revoked.length, 1);
    const before = e.calls.filter(call => call === 'blob').length;
    e.failure = null; e.confirm(); e.click('save'); assert.equal(e.downloads.length, 1);
    assert.equal(e.calls.filter(call => call === 'blob').length, before + 1);
  }
} else if (scenario === 'lifecycle_clear') {
  for (const action of [e => e.click('clear'), e => e.events.pagehide(), e => e.events.pageshow()]) {
    const e = setup(); e.input('note', 'private first note'); e.choose('approve'); e.click('next');
    e.input('note', 'private second note'); e.choose('reject'); ready(e); e.click('save');
    assert.equal(e.urls.length, 1); action(e); assertReset(e); assert.equal(e.revoked.length, 1);
    e.timersRun(); assert.equal(e.revoked.length, 1); e.click('next'); assert.equal(e.elements.note.value, ''); assert.equal(e.elements.decision.value, 'pending');
    assert.match(e.elements.status.textContent, /Source passages remain/);
  }
} else if (scenario === 'literal_long_content') {
  const e = setup();
  assert.equal(e.elements.passage.textContent, original.records[0].entry.principle);
  assert.ok(e.elements.passage.textContent.length > 19500); assert.ok(e.elements.passage.textContent.includes('\r\n\t'));
  assert.equal(e.elements.passage.children.length, 0);
  const meta = clone(original.records[0].entry); delete meta.principle;
  assert.deepEqual(JSON.parse(e.elements.metadata.textContent), meta);
  assert.equal(e.elements['record-heading'].textContent, 'Passage 1: ' + original.records[0].entry.title);
  assert.equal(e.elements.limits.children[0].textContent, original.limits[0]);
  assert.deepEqual(JSON.parse(e.elements.sources.textContent), original.sources);
  assert.ok(e.elements['record-revision'].textContent.includes(original.records[0].revision));
  assert.ok(e.elements['record-revision'].textContent.includes(original.records[0].entry.source_sha256));
  assert.ok(e.elements['record-revision'].textContent.includes(`[0, ${original.records[0].entry.source_byte_end})`));
  e.click('next'); assert.ok(!e.elements.passage.textContent.includes(original.records[0].entry.principle)); assertNoDownload(e);
} else if (scenario === 'report_byte_limit') {
  assert.equal(original.records.length, 256);
  const limit = 2 * 1024 * 1024;
  const serialized = notes => JSON.stringify({format:'jace-source-decisions-v1', draft_revision:original.draft_revision,
    reviewer:'Synthetic Reviewer', decisions:original.records.map((record, i) => ({entry_id:record.entry.entry_id,
      record_revision:record.revision, decision:'pending', note:notes[i]}))}, null, 2) + '\n';
  const boundaryNotes = target => {
    const notes = original.records.map(() => '');
    let remaining = target - Buffer.byteLength(serialized(notes), 'utf8');
    assert.ok(remaining > 0);
    for (let i = 0; i < notes.length; i++) {
      const stars = Math.min(2000, Math.floor(remaining / 4));
      notes[i] = '🌟'.repeat(stars); remaining -= stars * 4;
    }
    assert.ok(remaining >= 0 && remaining <= 3);
    if (remaining) {
      const index = notes.findIndex(note => [...note].length < 2000);
      assert.ok(index >= 0); notes[index] += ['', 'x', 'é', '€'][remaining];
    }
    assert.equal(Buffer.byteLength(serialized(notes), 'utf8'), target);
    assert.ok(notes.every(note => [...note].length <= 2000));
    return notes;
  };
  const populate = (e, notes) => {
    notes.forEach((note, i) => { e.input('note', note); if (i + 1 < notes.length) e.click('next'); });
    e.input('reviewer', 'Synthetic Reviewer');
  };
  for (const size of [limit - 1, limit]) {
    const e = setup(); populate(e, boundaryNotes(size)); e.confirm();
    assert.equal(e.elements.save.disabled, false, e.elements.status.textContent); e.click('save');
    assert.equal(e.attempts, 1); assert.equal(e.downloads.length, 1);
    assert.equal(Buffer.byteLength(e.blobs[0].text, 'utf8'), size); e.timersRun();
  }
  const excess = setup(); populate(excess, boundaryNotes(limit + 1)); excess.confirm();
  assert.equal(excess.elements['confirm-save'].checked, false); assert.equal(excess.elements.save.disabled, true);
  assert.match(excess.elements.status.textContent, /2 MiB UTF-8.*Shorten review notes/); assertNoDownload(excess);
  assert.equal(excess.blobs.length, 0); excess.click('save'); assertNoDownload(excess);
  const maximum = setup(); populate(maximum, original.records.map(() => '🌟'.repeat(2000))); maximum.confirm();
  assert.ok(Buffer.byteLength(serialized(original.records.map(() => '🌟'.repeat(2000))), 'utf8') > limit);
  assert.equal(maximum.elements['confirm-save'].checked, false); assert.equal(maximum.blobs.length, 0); assertNoDownload(maximum);
  assert.match(maximum.elements.status.textContent, /Shorten review notes/);
  // A silent field mutation is rechecked after confirmation is consumed and
  // before a Blob can be created, not merely at the checkbox event.
  const silent = setup(), exact = boundaryNotes(limit), over = boundaryNotes(limit + 1);
  populate(silent, exact); silent.confirm();
  assert.equal(silent.elements.save.disabled, false);
  assert.deepEqual(exact.slice(0, -1), over.slice(0, -1));
  silent.elements.note.value = over.at(-1); silent.click('save');
  assert.equal(silent.elements['confirm-save'].checked, false); assert.equal(silent.elements.save.disabled, true);
  assert.equal(silent.blobs.length, 0); assertNoDownload(silent);
  assert.match(silent.elements.status.textContent, /2 MiB UTF-8.*Shorten review notes/);
} else if (scenario === 'integration_report') {
  const e = setup();
  assert.equal(e.elements.review.hidden, false, e.elements.status.textContent);
  e.input('note', 'Synthetic approval for integration testing only.'); e.choose('approve');
  if (original.records.length > 1) {
    e.click('next'); e.input('note', 'Synthetic rejection for integration testing only.'); e.choose('reject');
  }
  ready(e); e.click('save'); e.click('save');
  assert.equal(e.attempts, 1); assert.equal(e.downloads.length, 1); assert.equal(e.blobs.length, 1);
  const report = e.report();
  assert.equal(report.reviewer, 'Synthetic Reviewer'); assert.equal(report.decisions.length, original.records.length);
  report.decisions.forEach((decision, i) => {
    assert.equal(decision.entry_id, original.records[i].entry.entry_id);
    assert.equal(decision.record_revision, original.records[i].revision);
    assert.equal(decision.decision, i === 0 ? 'approve' : i === 1 ? 'reject' : 'pending');
  });
  e.timersRun(); assert.equal(e.revoked.length, 1);
  assert.ok(process.argv[4], 'temporary report output path required');
  fs.writeFileSync(process.argv[4], e.blobs[0].text, {encoding:'utf8', flag:'wx', mode:0o600});
} else if (scenario === 'invalid_snapshots') {
  const mutators = [
    d => { d.protocol = 2; }, d => { d.kind = 'runtime'; }, d => { d.extra = 1; }, d => { d.draft_revision = 'z'.repeat(64); },
    d => { d.records = []; }, d => { d.sources = []; }, d => { d.limits = []; }, d => { d.limits = ['x'.repeat(4001)]; },
    d => { d.records[0].entry.verified = true; }, d => { d.records[0].entry.source_byte_end = 1; },
    d => { d.records[0].entry.source_byte_start = false; }, d => { d.records[0].entry.tags = ['dup','dup']; },
    d => { d.records[0].entry.title = '\ud800'; }, d => { d.records[0].entry.principle += 'tamper'; },
    d => { d.records[0].entry.entry_id = 'bad id'; }, d => { d.records[0].entry.extra = 'bad'; },
    d => { d.records[0].revision = 'b'.repeat(63); }, d => { d.records.push(clone(d.records[0])); },
    d => { d.sources.push(clone(d.sources[0])); }, d => { d.sources[0].byte_length = 1048577; },
    d => { d.sources.push({sha256:'d'.repeat(64),byte_length:1}); }, d => { delete d.records[0].entry.edition; }
  ];
  for (const mutate of mutators) {
    const value = clone(original); mutate(value); const e = setup(value);
    assert.equal(e.elements.review.hidden, true); assert.equal(e.elements.save.disabled, true); assertNoDownload(e);
    assert.match(e.elements.status.textContent, /invalid|exceeds/);
  }
} else throw new Error('Unknown scenario: ' + scenario);
console.log('PASS ' + scenario);
