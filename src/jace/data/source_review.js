/* Offline review only. Source strings are data, never HTML or executable code. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const controls = ['previous', 'next', 'decision', 'note', 'reviewer', 'confirm-save', 'save', 'clear'];
  const status = $('status');
  const DIGEST = /^[0-9a-f]{64}$/;
  const MAX_REPORT_BYTES = 2 * 1024 * 1024;
  const REPORT_SIZE_MESSAGE = 'The review report exceeds the 2 MiB UTF-8 file limit. Shorten review notes, then explicitly confirm again. Nothing was downloaded.';
  class ReportSizeError extends Error {}
  const UNSAFE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
  const TEXT_LIMITS = {entry_id:128, title:500, guidance:4000, source:1000, work:1000, language:64, location:1000, license:1000};
  const ENTRY_FIELDS = [...Object.keys(TEXT_LIMITS), 'principle', 'edition', 'tags', 'verified', 'source_sha256', 'source_byte_start', 'source_byte_end'];
  const bytes = value => new TextEncoder().encode(value).length;
  const requireValue = (ok, message) => { if (!ok) throw new Error(message); };
  const fields = (value, expected) => {
    requireValue(value !== null && typeof value === 'object' && !Array.isArray(value), 'Invalid review object.');
    const keys = Object.keys(value);
    requireValue(keys.length === expected.length && keys.every(key => expected.includes(key)), 'Invalid review fields.');
  };
  const text = (value, max, blank = false) => {
    requireValue(typeof value === 'string' && value.length <= max * 2 && [...value].length <= max &&
      (blank || value.trim().length > 0) && !UNSAFE.test(value) && !value.replace(/\r\n/g, '').includes('\r') &&
      !/[\ud800-\udfff]/.test(value.replace(/[\ud800-\udbff][\udc00-\udfff]/g, '')), 'Invalid or overlong review text.');
    return value;
  };
  const digest = value => requireValue(typeof value === 'string' && value.length === 64 && DIGEST.test(value), 'Invalid review digest.');
  function validateSnapshot(data) {
    fields(data, ['protocol', 'kind', 'draft_revision', 'sources', 'records', 'limits']);
    requireValue(data.protocol === 1 && data.kind === 'review_only', 'Unsupported review document.');
    digest(data.draft_revision);
    requireValue(Array.isArray(data.sources) && data.sources.length >= 1 && data.sources.length <= 32, 'Invalid review source count.');
    requireValue(Array.isArray(data.records) && data.records.length >= 1 && data.records.length <= 256, 'Invalid review record count.');
    requireValue(Array.isArray(data.limits) && data.limits.length >= 1 && data.limits.length <= 32, 'Invalid review limitations.');
    data.limits.forEach(value => text(value, 4000));
    const declared = new Map(), referenced = new Set(), ids = new Set();
    let total = 0;
    data.sources.forEach(source => {
      fields(source, ['sha256', 'byte_length']); digest(source.sha256);
      requireValue(!declared.has(source.sha256) && Number.isSafeInteger(source.byte_length) && source.byte_length >= 1 && source.byte_length <= 1048576, 'Invalid review source declaration.');
      declared.set(source.sha256, source.byte_length); total += source.byte_length;
    });
    requireValue(total <= 8388608, 'Review sources exceed their total byte limit.');
    const metadata = [];
    data.records.forEach(record => {
      fields(record, ['entry', 'revision']); digest(record.revision);
      const entry = record.entry; fields(entry, ENTRY_FIELDS);
      Object.entries(TEXT_LIMITS).forEach(([name, limit]) => text(entry[name], limit));
      requireValue(!/[\s\[\]]/u.test(entry.entry_id) && !ids.has(entry.entry_id), 'Invalid or duplicate review entry ID.');
      ids.add(entry.entry_id);
      requireValue(entry.verified === false, 'Review document must be unverified.');
      if (entry.edition !== null) text(entry.edition, 1000);
      requireValue(Array.isArray(entry.tags) && entry.tags.length <= 32, 'Invalid review tags.');
      entry.tags.forEach(tag => text(tag, 64));
      requireValue(new Set(entry.tags).size === entry.tags.length, 'Duplicate review tags.');
      text(entry.principle, 20000); digest(entry.source_sha256);
      const start = entry.source_byte_start, end = entry.source_byte_end;
      requireValue(declared.has(entry.source_sha256) && Number.isSafeInteger(start) && Number.isSafeInteger(end) && start >= 0 && end > start &&
        end <= declared.get(entry.source_sha256) && end - start <= 65536 && bytes(entry.principle) === end - start, 'Invalid exact-passage byte span.');
      referenced.add(entry.source_sha256);
      const meta = Object.fromEntries(Object.entries(entry).filter(([key]) => key !== 'principle'));
      metadata.push(meta);
    });
    requireValue(referenced.size === declared.size, 'Unreferenced review source.');
    requireValue(bytes(JSON.stringify(metadata)) <= 2097152, 'Review metadata exceeds its byte limit.');
    return data;
  }
  const deepFreeze = value => {
    if (value && typeof value === 'object') { Object.values(value).forEach(deepFreeze); Object.freeze(value); }
    return value;
  };
  let snapshot;
  try {
    const raw = $('review-snapshot').textContent;
    requireValue(bytes(raw) <= 12 * 1024 * 1024, 'Review document exceeds its byte limit.');
    snapshot = deepFreeze(validateSnapshot(JSON.parse(raw)));
  } catch (_) {
    status.textContent = 'This review document is invalid or exceeds its limits. No decisions can be saved. Rebuild it from the checked draft package.';
    controls.forEach(id => { $(id).disabled = true; });
    $('review').hidden = true;
    return;
  }

  let index = 0, states = [], confirmedReport = null, busy = false;
  const objectURLs = new Set();
  function revokeURLs() {
    for (const url of objectURLs) {
      try { URL.revokeObjectURL(url); } catch (_) { /* No retry or new download. */ }
    }
    objectURLs.clear();
  }
  function invalidateConfirmation() {
    confirmedReport = null; $('confirm-save').checked = false; $('save').disabled = true;
  }
  function syncCurrent() {
    const decision = $('decision').value, note = $('note').value;
    requireValue(['pending', 'approve', 'reject'].includes(decision), 'Unknown decision. Choose pending, approve or reject.');
    text(note, 2000, true);
    states[index] = {decision, note};
  }
  function reportText() {
    syncCurrent();
    const reviewer = text($('reviewer').value, 128);
    const decisions = snapshot.records.map((record, position) => {
      const state = states[position];
      requireValue(state && ['pending', 'approve', 'reject'].includes(state.decision), 'Unknown review decision.');
      text(state.note, 2000, state.decision === 'pending');
      return {entry_id:record.entry.entry_id, record_revision:record.revision, decision:state.decision, note:state.note};
    });
    const report = JSON.stringify({format:'jace-source-decisions-v1', draft_revision:snapshot.draft_revision, reviewer, decisions}, null, 2) + '\n';
    if (bytes(report) > MAX_REPORT_BYTES) throw new ReportSizeError(REPORT_SIZE_MESSAGE);
    return report;
  }
  function progress() {
    const counts = {pending:0, approve:0, reject:0};
    states.forEach(state => { if (Object.hasOwn(counts, state.decision)) counts[state.decision] += 1; });
    $('progress').textContent = `Passage ${index + 1} of ${snapshot.records.length}. Choices: ${counts.pending} pending, ${counts.approve} approve, ${counts.reject} reject. Approve and reject require a nonblank note before saving.`;
    $('previous').disabled = index === 0;
    $('next').disabled = index === snapshot.records.length - 1;
  }
  function renderRecord() {
    const record = snapshot.records[index];
    $('record-heading').textContent = `Passage ${index + 1}: ${record.entry.title}`;
    $('passage').textContent = record.entry.principle;
    $('metadata').textContent = JSON.stringify(Object.fromEntries(Object.entries(record.entry).filter(([key]) => key !== 'principle')), null, 2);
    $('record-revision').textContent = `Record revision: ${record.revision}\nUTF-8 byte span: [${record.entry.source_byte_start}, ${record.entry.source_byte_end}) (end-exclusive)\nSource SHA-256: ${record.entry.source_sha256}`;
    $('decision').value = states[index].decision;
    $('note').value = states[index].note;
    progress();
  }
  function resetPrivate() {
    revokeURLs(); index = 0; busy = false;
    states = snapshot.records.map(() => ({decision:'pending', note:''}));
    $('reviewer').value = ''; invalidateConfirmation(); renderRecord();
    status.textContent = 'Reviewer name, notes and decisions cleared. All records are pending. Source passages remain in this private HTML file and draft package.';
  }
  function edit() {
    invalidateConfirmation();
    try { syncCurrent(); progress(); status.textContent = 'Unsaved review changed. Confirm again when you are ready to save.'; }
    catch (_) { status.textContent = 'Invalid decision or note. Notes may contain at most 2,000 characters. Correct it before continuing.'; }
  }
  function navigate(offset) {
    try {
      syncCurrent();
      const next = index + offset;
      if (next >= 0 && next < snapshot.records.length) { index = next; renderRecord(); }
    } catch (_) { invalidateConfirmation(); status.textContent = 'Invalid decision or note. Correct it before changing passages.'; }
  }
  $('decision').onchange = edit;
  $('note').oninput = edit;
  $('reviewer').oninput = () => { invalidateConfirmation(); status.textContent = 'Reviewer name changed. Confirm again when you are ready to save.'; };
  $('previous').onclick = () => navigate(-1);
  $('next').onclick = () => navigate(1);
  $('clear').onclick = resetPrivate;
  $('confirm-save').onchange = () => {
    if (!$('confirm-save').checked) { invalidateConfirmation(); return; }
    try {
      confirmedReport = reportText(); $('save').disabled = false;
      status.textContent = 'Current report confirmed for one explicit save. It includes your name and notes.';
    } catch (error) {
      invalidateConfirmation();
      if (error instanceof ReportSizeError) { status.textContent = REPORT_SIZE_MESSAGE; return; }
      status.textContent = 'Cannot confirm: provide a reviewer name (1–128 characters), a valid decision for every passage, and a nonblank note (at most 2,000 characters) for each approve or reject.';
    }
  };
  $('save').onclick = () => {
    if (busy) return;
    const confirmed = $('confirm-save').checked && confirmedReport !== null;
    const expected = confirmedReport;
    // Consume before validation or any Blob/URL/download action, including failures.
    invalidateConfirmation();
    if (!confirmed) { status.textContent = 'Confirm the current report before saving. Nothing was downloaded.'; return; }
    let report;
    try {
      report = reportText();
      requireValue(report === expected, 'Review changed after confirmation.');
    } catch (error) { status.textContent = error instanceof ReportSizeError ? REPORT_SIZE_MESSAGE : 'Review changed or is invalid. Check it and explicitly confirm again. Nothing was downloaded.'; return; }
    busy = true;
    let anchor = null, url = null;
    try {
      const blob = new Blob([report], {type:'application/json;charset=utf-8'});
      url = URL.createObjectURL(blob); objectURLs.add(url);
      anchor = document.createElement('a'); anchor.href = url;
      anchor.download = 'jace-source-decisions.json'; anchor.hidden = true;
      document.body.append(anchor); anchor.click();
      status.textContent = 'One report download was requested. Check your browser downloads; this page cannot verify that a file was saved or control its permissions. No runtime corpus was created.';
    } catch (_) {
      status.textContent = 'The report download attempt failed or has an uncertain outcome. Check browser downloads before trying again. There is no automatic retry; any new attempt needs fresh confirmation.';
    } finally {
      if (anchor) { try { anchor.remove(); } catch (_) { /* No retry. */ } }
      if (url) {
        // Give the explicit click a short chance to resolve the blob URL, then
        // promptly release it. Page lifecycle events also revoke pending URLs.
        setTimeout(() => { if (objectURLs.has(url)) { try { URL.revokeObjectURL(url); } catch (_) { /* No retry. */ } objectURLs.delete(url); } }, 1000);
      }
      busy = false;
    }
  };
  window.addEventListener('pagehide', resetPrivate);
  window.addEventListener('pageshow', resetPrivate);
  $('draft-metadata').textContent = JSON.stringify({protocol:snapshot.protocol, kind:snapshot.kind, draft_revision:snapshot.draft_revision}, null, 2);
  $('sources').textContent = JSON.stringify(snapshot.sources, null, 2);
  snapshot.limits.forEach(limitation => { const item = document.createElement('li'); item.textContent = limitation; $('limits').append(item); });
  resetPrivate(); $('review').hidden = false;
})();
