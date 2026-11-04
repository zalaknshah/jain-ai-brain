'use strict';
// Browser adapter only. This does not provide STT/TTS models or translation.
const element = id => document.querySelector('#' + id);
const input = element('input');
const answer = element('answer');
const status = element('status');
const meta = document.querySelector('#meta small');
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let recognitionVersion = 0;
let requestVersion = 0;
let pendingRequest = null;
let speechVersion = 0;
let responseText = '';
let pendingPlayback = null;
let boundIdentity = null, learnConsent = null, requestSubmitted = false;
const MAX_RESPONSE_BYTES = 1024 * 1024;

function identitySnapshot() {
  return {user:element('user').value, token:element('token').value, rawApi:element('api').value, scope:element('memory-scope').value};
}
function sameIdentity(ctx) { return JSON.stringify(identitySnapshot()) === JSON.stringify(ctx); }
function clearLearning() { element('learn').checked = false; learnConsent = null; }
function clearPrivate(dropToken = false, scopeChanged = false) {
  const now = identitySnapshot();
  if (boundIdentity && (now.user !== boundIdentity.user || now.rawApi !== boundIdentity.rawApi)) dropToken = true;
  const uncertain = requestSubmitted;
  stopPlayback(); cancelPending(); cancelListening(); clearLearning();
  responseText = ''; input.value = ''; meta.textContent = '';
  element('speak-replies').checked = false; element('read').disabled = true;
  if (dropToken) element('token').value = '';
  boundIdentity = identitySnapshot();
  answer.textContent = scopeChanged ? 'Memory scope changed. Previous draft and reply cleared.' : 'Connection details changed. Previous draft and reply cleared. Enter the assigned token and a new question.';
  status.textContent = uncertain ? 'Private view cleared. A request already sent may still finish or save an opted-in memory. No automatic retry.' : 'Private view cleared. Nothing is sent automatically.';
}
function guardIdentity() {
  if (boundIdentity && !sameIdentity(boundIdentity)) {
    const now = identitySnapshot();
    clearPrivate(now.user !== boundIdentity.user || now.rawApi !== boundIdentity.rawApi || now.token !== boundIdentity.token, now.scope !== boundIdentity.scope);
    return false;
  }
  return true;
}
function editedQuestion() {
  if (!guardIdentity()) return;
  const uncertain = requestSubmitted;
  stopPlayback(); cancelPending(); cancelListening(); clearLearning();
  responseText = ''; element('read').disabled = true; answer.textContent = ''; meta.textContent = '';
  status.textContent = uncertain ? 'Question changed. A request already sent may still finish or save its opted-in memory. Review before sending again.' : 'Question changed. Review it and choose learning again if wanted.';
}
function current(version, ctx, rawInput) {
  if (version !== requestVersion || !guardIdentity()) return false;
  if (!sameIdentity(ctx) || input.value !== rawInput) { editedQuestion(); return false; }
  return true;
}
function connection() {
  const ctx = identitySnapshot();
  if (!ctx.user.trim() || ctx.user.length > 200) throw new Error('Enter the exact assigned user ID.');
  if (ctx.scope !== ctx.scope.trim() || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(ctx.scope)) throw new Error('Enter a valid memory scope before sending. Blank or malformed scopes do not fall back to default.');
  if (ctx.token.length < 32 || ctx.token.length > 4096 || /[^\x21-\x7e]/.test(ctx.token)) throw new Error('Enter your assigned API token. It is kept only in this page.');
  if (ctx.rawApi !== ctx.rawApi.trim() || /[\x00-\x20\x7f]/.test(ctx.rawApi)) throw new Error('Review the API address; whitespace is not permitted.');
  let url; try { url = new URL(ctx.rawApi); } catch (_) { throw new Error('Enter a valid trusted API origin.'); }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      !(url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1','[::1]','localhost'].includes(url.hostname)))) throw new Error('Use a trusted HTTPS or local loopback API origin without path, credentials, query or fragment.');
  return {identity:ctx, api:url.origin};
}
async function boundedJSON(response, version, ctx, rawInput) {
  const declared = response.headers.get('content-length');
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_RESPONSE_BYTES)) throw new Error('API response exceeds the review limit.');
  if (!response.body || typeof response.body.getReader !== 'function') throw new Error('Streaming response support is required to read private replies safely.');
  const reader = response.body.getReader(), parts = []; let bytes = 0;
  try {
    while (true) {
      if (!current(version,ctx,rawInput)) throw new Error('View changed.');
      const part = await reader.read();
      if (!current(version,ctx,rawInput)) throw new Error('View changed.');
      if (part.done) break;
      if (!(part.value instanceof Uint8Array)) throw new Error('Invalid response stream.');
      bytes += part.value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new Error('API response exceeds the review limit.');
      parts.push(part.value);
    }
  } catch (error) { try { await reader.cancel(); } catch (_) { /* No retry. */ } throw error; }
  finally { reader.releaseLock(); }
  const data = new Uint8Array(bytes); let offset = 0;
  for (const part of parts) { data.set(part,offset); offset += part.byteLength; }
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(data));
}

function stopPlayback() {
  speechVersion += 1;
  pendingPlayback = null;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
}

function cancelListening() {
  recognitionVersion += 1;
  const old = recognition;
  if (old) {
    try { old.abort(); } catch (_) { /* Wait for onend; do not assume capture stopped. */ }
  }
  element('listen').disabled = !Recognition || recognition !== null;
  element('stop').disabled = true;
}

function cancelPending() {
  requestVersion += 1;
  if (pendingRequest) pendingRequest.abort();
  pendingRequest = null; requestSubmitted = false;
}

function stopReply() {
  if (!guardIdentity()) return;
  const wasPending = pendingRequest !== null, wasSent = requestSubmitted;
  clearLearning();
  stopPlayback();
  cancelPending();
  cancelListening();
  if (wasPending) answer.textContent = 'Stopped waiting for this reply.';
  status.textContent = wasSent
    ? 'Stopped waiting. A request already sent may still finish or save an opted-in memory on the server.'
    : 'Playback and listening stopped.';
}

function startListening() {
  if (!guardIdentity() || !Recognition || recognition) return;
  cancelPending();
  stopPlayback();
  clearLearning();
  const captureIdentity = identitySnapshot(), captureInput = input.value;
  const version = ++recognitionVersion;
  const current = new Recognition();
  recognition = current;
  current.lang = element('language').value;
  current.interimResults = false;
  current.continuous = false;
  let received = false;
  current.onresult = event => {
    if (version !== recognitionVersion || recognition !== current || !guardIdentity()) return;
    if (!sameIdentity(captureIdentity) || input.value !== captureInput) { editedQuestion(); return; }
    if (received) return;
    const text = Array.from(event.results).map(result => result[0].transcript).join(' ').trim();
    if (!text) return;
    received = true;
    input.value = text;
    clearLearning();
    status.textContent = 'Transcript ready. Review it, then choose Ask JACE. Nothing has been sent to JACE yet.';
  };
  current.onerror = () => {
    if (version !== recognitionVersion || recognition !== current || !guardIdentity()) return;
    status.textContent = 'Dictation is unavailable or was denied. You can still type your question.';
    received = true; // Preserve the error status when onend follows.
  };
  current.onend = () => {
    if (recognition !== current) return;
    recognition = null;
    element('listen').disabled = false;
    element('stop').disabled = true;
    if (version === recognitionVersion && !guardIdentity()) return;
    if (version === recognitionVersion && !received) status.textContent = 'No transcript received. Try again or type your question.';
    const queued = pendingPlayback;
    pendingPlayback = null;
    if (queued) queued();
  };
  try {
    current.start();
    element('listen').disabled = true;
    element('stop').disabled = false;
    status.textContent = 'Listening. Your browser handles speech recognition; review the transcript before sending.';
  } catch (_) {
    recognitionVersion += 1;
    recognition = null;
    element('listen').disabled = !Recognition;
    element('stop').disabled = true;
    status.textContent = 'Could not start dictation. You can still type your question.';
  }
}

function readResponse() {
  if (!guardIdentity()) return;
  stopPlayback();
  if (!responseText) return;
  const version = speechVersion;
  if (recognition) {
    // Fail closed: request abort, but wait for the browser's end event before
    // playback. This is not a verification of physical microphone timing.
    pendingPlayback = () => { if (version === speechVersion) playResponse(); };
    status.textContent = 'Waiting for the browser to end dictation before playback. You can cancel this reply.';
    cancelListening();
    return;
  }
  playResponse();
}

function playResponse() {
  if (!guardIdentity() || !responseText) return;
  const synthesis = window.speechSynthesis;
  if (!synthesis || !window.SpeechSynthesisUtterance) {
    status.textContent = 'Speech playback is unavailable. The text response remains available.';
    return;
  }
  const language = element('language').value.toLowerCase();
  const voices = synthesis.getVoices();
  const voice = voices.find(item => item.lang.toLowerCase() === language)
    || voices.find(item => item.lang.toLowerCase().split('-')[0] === language.split('-')[0]);
  if (!voice) {
    status.textContent = 'No matching speech voice is available yet. Try again after voices load, choose another voice language, or read the text.';
    return;
  }
  const version = speechVersion;
  const utterance = new window.SpeechSynthesisUtterance(responseText);
  utterance.lang = voice.lang;
  utterance.voice = voice;
  utterance.onend = () => { if (version === speechVersion && guardIdentity()) status.textContent = 'Playback finished.'; };
  utterance.onerror = () => { if (version === speechVersion && guardIdentity()) status.textContent = 'Playback stopped or failed. The text response remains available.'; };
  try {
    synthesis.speak(utterance);
    status.textContent = 'Reading the response. Voice selection does not translate its text.';
  } catch (_) {
    status.textContent = 'Speech playback failed. The text response remains available.';
  }
}

async function ask() {
  if (!guardIdentity()) return;
  const rawInput = input.value, text = rawInput.trim();
  if (!text) return;
  const requestedLearning = element('learn').checked, consent = learnConsent;
  clearLearning(); // Consume before validation or asynchronous work.
  const identity = identitySnapshot();
  if (requestedLearning && (!consent || consent.rawInput !== rawInput || JSON.stringify(consent.identity) !== JSON.stringify(identity))) {
    stopPlayback(); cancelPending(); cancelListening(); responseText = ''; element('read').disabled = true; meta.textContent = '';
    answer.textContent = 'Learning choices changed or were restored. Review this message and check learning again before sending.';
    return;
  }
  let ctx, api;
  try {
    ({identity:ctx,api} = connection());
    if (rawInput.length > 10000) throw new Error('Enter a question of at most 10,000 characters.');
  } catch (error) {
    stopPlayback(); cancelListening(); cancelPending(); responseText = ''; element('read').disabled = true;
    answer.textContent = error.message; meta.textContent = ''; return;
  }
  stopPlayback(); cancelListening(); cancelPending();
  const version = requestVersion, controller = new AbortController();
  pendingRequest = controller;
  responseText = ''; element('read').disabled = true; answer.textContent = 'Thinking…'; meta.textContent = '';
  status.textContent = 'Checking the API before sending this message. Nothing is retried automatically.';
  const options = {signal:controller.signal, redirect:'error', credentials:'omit', cache:'no-store'};
  try {
    const capability = await fetch(api + '/health', {...options, method:'GET', headers:{Accept:'application/json'}});
    if (!current(version,ctx,rawInput)) return;
    const support = await boundedJSON(capability,version,ctx,rawInput);
    if (!current(version,ctx,rawInput)) return;
    if (!capability.ok || support.memory_scope_protocol !== 1) throw new Error('This API does not confirm scoped recall support. No question was sent.');
    requestSubmitted = true;
    const response = await fetch(api + '/v1/think', {...options,
      method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer ' + ctx.token},
      body:JSON.stringify({user_id:ctx.user,input:text,learn:requestedLearning,memory_scope:ctx.scope})});
    if (!current(version,ctx,rawInput)) return;
    const data = await boundedJSON(response,version,ctx,rawInput);
    if (!current(version,ctx,rawInput)) return;
    if (!response.ok) throw new Error('API request failed (' + response.status + ').');
    if (data.memory_scope !== ctx.scope) throw new Error('The API did not confirm the selected memory scope. No reply is displayed.');
    if (data.user_id !== ctx.user || data.input !== text) throw new Error('The API did not confirm the submitted question and owner. No reply is displayed.');
    if (typeof data.response !== 'string' || data.response.length > 40000) throw new Error('Invalid response from JACE');
    requestSubmitted = false;
    responseText = data.response; answer.textContent = responseText; element('read').disabled = false;
    meta.textContent = `scope: ${ctx.scope} · ${data.ethical_assessment?.risk_level || 'unknown'} risk · ${data.perspectives?.length || 0} perspectives · ${data.canonical_evidence?.length || 0} source record(s)`;
    status.textContent = 'Response ready. Voice language does not translate its text.';
    if (element('speak-replies').checked) readResponse();
  } catch (error) {
    if (!current(version,ctx,rawInput)) return;
    const uncertain = requestSubmitted;
    answer.textContent = error.name === 'AbortError' ? 'Request cancelled in this page.' : error.message;
    status.textContent = 'No new response is available. No automatic retry.' + (uncertain ? ' A submitted request may still finish or save an opted-in memory; check before sending again.' : ' Check the API address and authorization.');
  } finally {
    if (version === requestVersion) { pendingRequest = null; requestSubmitted = false; }
  }
}

element('listen').disabled = !Recognition;
element('listen').onclick = startListening;
element('stop').onclick = () => {
  if (!guardIdentity()) return;
  if (!recognition) return;
  try {
    recognition.stop();
    element('stop').disabled = true;
    status.textContent = 'Finishing dictation. Review the transcript before sending.';
  } catch (_) { cancelListening(); }
};
element('send').onclick = ask;
element('cancel').onclick = stopReply;
element('read').onclick = readResponse;
element('language').onchange = () => {
  if (!guardIdentity()) return;
  stopPlayback();
  cancelListening();
  status.textContent = 'Voice language changed. This does not translate text or change JACE reasoning capabilities.';
};
for (const id of ['user','token','api','memory-scope']) {
  const changed = () => clearPrivate(id === 'user' || id === 'api', id === 'memory-scope');
  element(id).oninput = changed; element(id).onchange = changed;
}
input.oninput = editedQuestion; input.onchange = editedQuestion;
element('learn').onchange = () => {
  if (!guardIdentity()) return;
  learnConsent = element('learn').checked ? {identity:identitySnapshot(),rawInput:input.value} : null;
};
window.addEventListener('pagehide', () => clearPrivate(true));
window.addEventListener('pageshow', () => clearPrivate(true));
clearLearning(); element('speak-replies').checked = false; boundIdentity = identitySnapshot();
if (!Recognition) status.textContent = 'Dictation is unsupported in this browser. Type your question instead.';
