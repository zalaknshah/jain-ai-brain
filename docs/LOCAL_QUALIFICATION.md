# Local use and browser/audio qualification

JACE can run as a local command-line prototype. That is distinct from a hosted
product or a qualified voice application. This guide separates what can be used
now from the decisions and observations still needed.

## Use the text prototype without a provider

Use an authorized checkout and Python 3.10 or newer. The core has no runtime
third-party dependencies. From the checkout, on Linux/macOS:

```sh
export PYTHONPATH=src
export JACE_LLM_URL=
export JACE_LLM_API_KEY=
export JACE_CANONICAL_PATH=
export JACE_DB_PATH=/absolute/private/path/jace-demo.sqlite3
python -m jace.cli source-capabilities
python -m jace.cli health
python -m jace.cli ask "How can I clean a small desk using less water?"
```

Choose a new database path in a private directory you own, not an existing
personal database. `health` and `ask` initialize a local database and canonical
graph. `ask` does not opt in to conversational learning unless `--learn` is
passed, but it can still create operational/audit records. This is not a
read-only or ephemeral command. Do not use sensitive information for a smoke
test. `source-capabilities` alone does not initialize an engine or database.

The empty model URL keeps this run on `LocalReasoner`; it does not contact a
model provider. The empty canonical path selects the six packaged sample
principles, not the collected Agama files. Check `health` for `LocalReasoner`
and six entries before treating the result as this baseline. Generic answers
can remain templates, including for reasonable questions outside the narrow
authored planner triggers. Running the command does not establish learned Jain
reasoning or useful retrieval from actual scripture.

Windows can use the core CLI with the equivalent environment assignments in
its shell. Native Windows exact-source review, bundle publication and external
source admission are not implemented. A successful core health check does not
clear that gate. See [source platform requirements](SOURCE_PLATFORMS.md).

An offline wheel can be built from a trusted checkout when the build tools are
already installed:

```sh
python -m pip wheel --no-index --no-deps --no-build-isolation . --wheel-dir dist
python -m pip install --no-index --no-deps dist/jace-0.1.0-py3-none-any.whl
```

Install into an environment you control. These commands do not download missing
build tools. The wheel supplies the core CLI and package data; the browser pages
in `web/`, research files and training fixtures are checkout assets, not a
packaged desktop application.

## Choose a deployment destination before exposing a service

The smallest decision is **private local use on an approved Linux/POSIX machine
or a public HTTPS host**. Local CLI use needs neither a hosting account nor an
API token. Actual browser access must use a route allowed by the operator and
the execution environment. A blocked route is not permission to use another
protocol, tunnel, proxy, mirror or executor to reach the same denied target.

For a local API, use loopback binding and a deliberately private database. An
operator must separately authorize and provision any persistent API credentials.
Do not paste real tokens into examples or logs. Without configured authorization,
the API remains locked except for public health information. The browser text
console additionally needs an approved origin and access route.

The checked-in Docker/Compose recipe is not a verified public deployment. It
publishes port 8787 on all host interfaces by default, has no TLS termination,
and does not provision credentials. Do not use that recipe unchanged to expose
a shared machine or Internet endpoint. No Docker execution is implied by the
package smoke test below.

A public deployment additionally needs an explicitly selected account/host,
approved exposure and budget, HTTPS, credential lifecycle, origin restrictions,
retention/backups, resource/abuse controls, and rights clearance for every served
source. A free tier is not a guaranteed zero-cost commitment. Public deployment
must not publish the private research collection or silently enable a provider.

## Real browser and audio acceptance record

Run this only after an allowed browser route is available. Use synthetic text,
a disposable test identity/database, and existing test authorization. Record the
exact commit, OS, browser/version, route/origin, timestamp and test outcome. Mark
untested rows **not run**, unsupported features **unsupported**, and failures
**failed**. A browser-script fixture is not a substitute for these observations.

1. **Rendering and navigation:** check every console page, keyboard focus, labels,
   zoom, narrow viewport and screen-reader status announcements. Check Back,
   Forward, reload and restored pages; private replies and consent must not
   unexpectedly reappear. Capture only synthetic information in screenshots.
2. **Text and identity:** send a synthetic question with learning unchecked.
   Check correct owner/scope, response rendering, invalid credentials and changed
   owner/API/scope while a request is pending. No stale private reply should be
   displayed. A cancelled request may already have completed on the server;
   inspect the synthetic database before retrying any mutation.
3. **Permission denial and unsupported audio:** deny microphone access once.
   Confirm that typing still works and no repeated permission request occurs
   without a new user action. Record missing recognition/voice support honestly.
   Do not change browser security settings or grant unexpected permissions to
   make a test pass.
4. **Dictation privacy:** inspect the browser's documented speech processing
   destination before permitting capture. Web Speech recognition may transmit
   audio to the browser provider before any JACE submission. Transcript review
   only delays sending text to JACE; it does not make recognition local or undo
   audio already transmitted. Use non-personal test phrases and obtain approval
   for any required microphone/service permission.
5. **Recognition:** separately test English, Hindi and Gujarati with scripted
   original phrases. Record the expected phrase and actual transcript, omissions,
   substitutions and latency. Check Stop, repeated Dictate, language changes,
   silence and interruption. Recognition must not itself send or learn text.
   Language selection does not prove translation or multilingual reasoning.
6. **Playback:** list actual matching voices and whether the browser marks them
   local. Check opt-in read-aloud, manual Read response, Stop, a newer response,
   identity changes, unavailable voices and a microphone still shutting down.
   Do not treat a local-service flag as a comprehensive privacy certification.
7. **Source review/downloads:** on a supported platform, use only an original
   synthetic source pack. Check the real file picker, report save/import, stale
   import cancellation and export. Report whether actual files match expected
   bytes and whether browser download prompts complete. Do not load private or
   uncleared corpus files merely to exercise the workflow.

The Web Speech adapter is not streaming STT/TTS infrastructure, a measured
full-duplex voice system, or a guarantee of offline operation. Real audio quality,
microphone release timing, device support and provider privacy need observation.

## Baseline evidence, 5 November 2026

Against the tree shared by main `019722e602a832f3b8093d19d558dd960a91cca1`:

- 34 voice-console checks passed: 32 simulated browser-API/JavaScript checks and
  two JavaScript-to-Python synthetic loopback checks. No actual browser or audio
  device was involved.
- An offline wheel built and installed without dependencies or downloads. From
  outside the checkout, the installed CLI returned healthy `LocalReasoner`, six
  sample entries, a text answer with explicit grounding limits, and Linux source
  prerequisites. Only a fresh synthetic database was used.
- Browser rendering, microphone, real recognition/playback, file-picker/download,
  native Windows exact-source IO, Docker, HTTPS and hosted availability were not
  qualified. The browser access denial remains in force.

These results establish a runnable local text baseline, not completion of the
product or a new public deployment. Revalidate changed code and the selected
platform before extending the claim.
