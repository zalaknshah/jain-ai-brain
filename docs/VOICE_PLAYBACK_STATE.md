# Voice playback opt-out state

The browser conversation console separates automatic read-aloud from an explicit
**Read response** click. Unchecking **Read replies aloud** cancels a queued or
active automatic reply. The response text stays available. Rechecking the box
does not restart the cancelled reply; a later response can be read automatically.
An explicit manual read still works with the checkbox unchecked.

An automatic reply can be queued while the browser finishes ending dictation.
The adapter waits for the recognition `end` event before dispatching speech and
rechecks automatic read-aloud consent at that point. Checkbox input/change events
also invalidate pending playback and old speech callbacks. These checks request
cancellation through the browser API; they do not establish physical microphone
release timing or how quickly audible speech stops.

## Regression evidence

A hardware-free reproduction against base `07a69a11` dispatched speech after the
automatic read-aloud box was unchecked during recognition shutdown. Five added
Node VM scenarios cover pending cancellation (including a silent field change),
active cancellation and stale callbacks, preserved manual playback, no restart
after repeated toggles, and opting out before an asynchronous reply arrives.

The complete voice-console test file has 39 checks: 37 simulated JavaScript/API
state scenarios and two synthetic Node-to-Python loopback cases. Independent
review additionally exercised manual takeover, failure cleanup and synchronous
recognition-end ordering.

This is software state evidence only. It does not qualify a real browser,
microphone, recognition engine, speech voice, pronunciation, accents, device
support or audio latency. No speech model or audio transport was added. See the
[local qualification guide](LOCAL_QUALIFICATION.md) for the remaining browser,
media-permission and deployment gates.
