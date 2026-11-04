# Optional model transport deadline

This change prevents a slow or trickling HTTP response from holding the optional model call open indefinitely under a per-socket inactivity timeout. It does not add a model, authorize provider access, qualify provider compatibility or make the prototype production-ready. Development and tests use only synthetic local loopback fixtures.

## Boundary

The default `HttpJsonReasoner` creates one local worker for one explicitly configured JSON POST. The parent validates the fixed request shape, URL, authorization and 128 KiB body limit, then passes a separately bounded 224 KiB JSON/base64 envelope through stdin. No request, credential or raw provider output is written to a temporary file, command-line argument or environment variable by this transport.

The interpreter and packaged worker use absolute paths. `-I -S` disables user Python paths and site startup hooks. The worker imports only the Python standard library and does not initialize JACE's engine, corpus or memory. The environment keeps only Windows system locations when present; inherited proxies, provider keys, Python settings and custom TLS overrides are excluded. The launch uses no shell and closes unrelated descriptors. This is process/startup isolation, **not an operating-system security sandbox**: a compromised interpreter, installation or machine is outside this boundary.

The parent owns a 30-second `subprocess.run` communication timeout covering worker stdin, network work, response collection and exit. The worker also retains a socket timeout. The parent kills and reaps the direct worker on communication timeout and does not automatically retry. Slow DNS, TLS, headers and bodies occur in that worker, rather than leaving a background network thread in the engine process.

Process creation and OS kill/reaping can add time, so the timeout is not a hard real-time or whole-service latency guarantee. The engine's existing global lock remains held during the attempt. Other requests can queue behind multiple attempts. There is no new user cancellation API, queue admission policy or capacity guarantee.

## Destination and response protections

- HTTPS remains required except for HTTP literal loopback IP addresses. Embedded URL credentials, fragments and invalid authorities are rejected. A configured endpoint remains an operator responsibility, not a verified provider identity.
- Redirects are rejected, including same-host redirects. Inherited HTTP proxies are disabled. This transport does not discover or switch destinations or automatically retry failed POSTs.
- Only status 200 and an absent or single `identity` Content-Encoding field are accepted. Conflicting or duplicate encodings are rejected.
- Duplicate/invalid Content-Length, conflicting transfer/length headers, unsupported transfer encodings and declared-length truncation are rejected. Standard chunked bodies must complete successfully.
- Response reads remain capped at 64 KiB plus one overflow-detection byte. The worker emits only a complete bounded read after these checks; failures return no partial provider output or diagnostic text. The parent rechecks the exit code and byte bound, then the existing structured-output/citation checks still apply.
- A transport failure uses the existing labeled local rule-based fallback. Refusals, source matching, selected-context revision checks and action confirmation requirements remain unchanged.

A timeout does not reveal whether the provider received or completed the POST. Killing local work cannot recall transmitted context, cancel already accepted provider computation, prevent retained data or ensure that no charge occurred. Before explicitly retrying, the operator must consider possible duplicate work and costs. Existing consent, privacy, retention and provider-account gates still apply.

## Evidence and compatibility limits

`tests/test_model_transport.py` uses original synthetic payloads and a real local HTTP fixture. It checks successful answers; stalled headers; headers and bodies trickling faster than socket inactivity limits; direct-child exit after timeout; no automatic retry; fallback; engine-lock availability after failure; response size/encoding/status/framing failures; redirects; isolated startup; private stdin transport; schema bounds; and content-free failure behavior. Existing context-selection and model-output tests remain applicable. Timing assertions include scheduling tolerance and are regressions, not latency benchmarks.

The worker must be present as a regular packaged Python file and the running interpreter must support subprocess execution. Missing workers, spawn restrictions and unsupported packaged/frozen layouts fail closed through local fallback. Custom proxy/CA environment configurations are deliberately not inherited and require separate design and review. Source-tree and installed-wheel synthetic execution are checked on Linux; native Windows/macOS, production TLS/provider behavior, remote cancellation and heavily loaded service behavior are not qualified by these tests. Native Windows exact-source IO remains unsupported, independently of this transport.
