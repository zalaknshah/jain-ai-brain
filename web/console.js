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
  pendingRequest = null;
}

function stopReply() {
  const wasPending = pendingRequest !== null;
  stopPlayback();
  cancelPending();
  cancelListening();
  if (wasPending) answer.textContent = 'Stopped waiting for this reply.';
  status.textContent = wasPending
    ? 'Stopped waiting. A request already sent may still finish or save an opted-in memory on the server.'
    : 'Playback and listening stopped.';
}

function startListening() {
  if (!Recognition || recognition) return;
  cancelPending();
  stopPlayback();
  element('learn').checked = false;
  const version = ++recognitionVersion;
  const current = new Recognition();
  recognition = current;
  current.lang = element('language').value;
  current.interimResults = false;
  current.continuous = false;
  let received = false;
  current.onresult = event => {
    if (version !== recognitionVersion || recognition !== current) return;
    const text = Array.from(event.results).map(result => result[0].transcript).join(' ').trim();
    if (!text) return;
    received = true;
    input.value = text;
    element('learn').checked = false;
    status.textContent = 'Transcript ready. Review it, then choose Ask JACE. Nothing has been sent to JACE yet.';
  };
  current.onerror = () => {
    if (version !== recognitionVersion || recognition !== current) return;
    status.textContent = 'Dictation is unavailable or was denied. You can still type your question.';
    received = true; // Preserve the error status when onend follows.
  };
  current.onend = () => {
    if (recognition !== current) return;
    recognition = null;
    element('listen').disabled = false;
    element('stop').disabled = true;
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
  utterance.onend = () => { if (version === speechVersion) status.textContent = 'Playback finished.'; };
  utterance.onerror = () => { if (version === speechVersion) status.textContent = 'Playback stopped or failed. The text response remains available.'; };
  try {
    synthesis.speak(utterance);
    status.textContent = 'Reading the response. Voice selection does not translate its text.';
  } catch (_) {
    status.textContent = 'Speech playback failed. The text response remains available.';
  }
}

async function ask() {
  const text = input.value.trim();
  if (!text) return;
  const memoryScope = element('memory-scope').value;
  if (memoryScope !== memoryScope.trim() || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(memoryScope)) {
    stopPlayback(); cancelListening(); cancelPending();
    responseText = ''; element('read').disabled = true;
    answer.textContent = 'Enter a valid memory scope before sending. Blank or malformed scopes do not fall back to default.';
    return;
  }
  const token = element('token').value;
  const api = element('api').value.replace(/\/$/, '');
  const user = element('user').value;
  if (!token) {
    cancelPending();
    stopPlayback();
    responseText = '';
    element('read').disabled = true;
    answer.textContent = 'Enter your assigned API token. It is kept only in this page.';
    return;
  }
  stopPlayback();
  cancelListening();
  cancelPending();
  const version = requestVersion;
  const controller = new AbortController();
  pendingRequest = controller;
  const learn = element('learn').checked;
  element('learn').checked = false;
  responseText = '';
  element('read').disabled = true;
  answer.textContent = 'Thinking…';
  meta.textContent = '';
  status.textContent = 'Waiting for JACE. Stopping here cannot undo work already accepted by the server.';
  try {
    const capability = await fetch(api + '/health', {method: 'GET', signal: controller.signal, headers: {'Accept': 'application/json'}});
    const support = await capability.json();
    if (version !== requestVersion) return;
    if (!capability.ok || support.memory_scope_protocol !== 1) throw new Error('This API does not confirm scoped recall support. No question was sent.');
    const response = await fetch(api + '/v1/think', {
      method: 'POST', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
      body: JSON.stringify({user_id: user, input: text, learn, memory_scope: memoryScope})
    });
    const data = await response.json();
    if (version !== requestVersion) return;
    if (!response.ok) throw new Error(data.error || 'Request failed');
    if (data.memory_scope !== memoryScope) throw new Error('The API did not confirm the selected memory scope. No reply is displayed.');
    if (typeof data.response !== 'string') throw new Error('Invalid response from JACE');
    responseText = data.response;
    answer.textContent = responseText;
    element('read').disabled = false;
    meta.textContent = `scope: ${memoryScope} · ${data.ethical_assessment?.risk_level || 'unknown'} risk · ${data.perspectives?.length || 0} perspectives · ${data.canonical_evidence?.length || 0} source record(s)`;
    status.textContent = 'Response ready. Voice language does not translate its text.';
    if (element('speak-replies').checked) readResponse();
  } catch (error) {
    if (version !== requestVersion) return;
    answer.textContent = error.name === 'AbortError' ? 'Request cancelled in this page.' : error.message;
    status.textContent = 'No new response is available. Check the API address and authorization before retrying.';
  } finally {
    if (version === requestVersion) pendingRequest = null;
  }
}

element('listen').disabled = !Recognition;
element('listen').onclick = startListening;
element('stop').onclick = () => {
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
  stopPlayback();
  cancelListening();
  status.textContent = 'Voice language changed. This does not translate text or change JACE reasoning capabilities.';
};
for (const id of ['user', 'token', 'api', 'memory-scope']) {
  element(id).oninput = () => {
    stopPlayback();
    cancelListening();
    cancelPending();
    element('learn').checked = false;
    responseText = '';
    input.value = '';
    if (id === 'user' || id === 'api') element('token').value = '';
    element('read').disabled = true;
    answer.textContent = id === 'memory-scope'
      ? 'Memory scope changed. Previous draft and reply cleared. Requests already accepted may still finish in the prior scope.'
      : 'Connection details changed. Previous draft and reply cleared. Enter the assigned token and a new question.';
    meta.textContent = '';
  };
}
window.addEventListener('pagehide', () => { stopPlayback(); cancelPending(); cancelListening(); });
if (!Recognition) status.textContent = 'Dictation is unsupported in this browser. Type your question instead.';
