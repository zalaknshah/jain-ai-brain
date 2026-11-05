# Independent resource-verdict review

## Finding
The correction accurately rejects the archived installed nominal report for its observed CPU overage while preserving the physical completion evidence. No blocking defect was found in the narrow observed-counter classification. This is not a physical rerun, full-lifetime resource qualification, or resolution of signal-9 reliability.

The exact archived SHA-256 is 951a23445ad0347ed2c2460ad63ac2739781ffb9a6dbbd5c3fcea4f416d08115. Its 5,000 steps, 20.000000000000018 simulated seconds, three physical acceptance flags, terminal reason step_budget_reached and 0.1947829426938574 m advance remain unchanged. Its 15.80148 CPU seconds exceeds 15; worker wall 24.875193871033844 and outer wall 25.074059182952624 are below 30. Directly applying the helper produces physical_six_step_criteria_met=true, observed_resource_budget_satisfied=false, sustained_probe_accepted=false and only worker_cpu_seconds_used_exceeded. Every original field except sustained_probe_accepted is preserved exactly.

## Source and accounting
All 17 implementation hashes in the corrective freeze and the archived report hash matched before checks and again after tests. The controller hash remains 280ba566c9110666209d2e9d4374734561c14b43c65e25723a74aaf79d573f03. The installed-smoke-report identifies original commit f8a86edb1bcd421f2ff344753b821068c28a5238, outside-checkout installation, no dependency installations, the same controller hash, and matching nominal counters.

The worker sample uses resource.getrusage(resource.RUSAGE_SELF).ru_utime + ru_stime. This is cumulative worker process CPU, including startup/imports/setup/simulation/report construction, with no startup subtraction and no parent/sibling CPU. It excludes subsequent verdict construction, JSON/output and exit. The helper explicitly disclaims full-worker-lifetime CPU measurement and resource-reliability qualification. Worker elapsed begins at _run entry rather than process launch. Launcher elapsed covers subprocess completion and parsing before its final verdict. These boundaries are accurately documented.

The helper requires exact integer 1 GiB address-space and 15-second CPU configured limits. The launcher additionally supplies and checks its actual configured 30-second timeout; the worker stage does not claim to measure outer wall time. CPU and wall counters must be native int/float, finite and nonnegative, and cannot exceed exact thresholds. Boolean/string/missing/negative/nonfinite values fail closed. Equality at the budget passes intentionally; the unchanged real performance tests still require strict headroom. Physical metrics/controller/model and historical tests are unchanged.

## Checks run
Only authorized nonphysics checks ran:
- 9 resource verdict tests and 7 SustainedContractTests: all 16 passed in 0.120 seconds. The CLI contract test invokes only the unconfirmed rejection path, not physics.
- Direct classification of the actual archived report, preserving every original field except acceptance.
- 19 additional pure malformed-counter/configuration cases (including negative infinity, false, list, dict and huge integer counters): all rejected.
- A mocked launcher malformed-resource_limits reproduction.

No physics, full suite, installation, network, email, tracing, cap change, controller tuning, publication or commit was performed.

## Nonblocking pre-existing hardening issue
freebase_sustained.py sets report.setdefault('resource_limits', {})['outer_wall_seconds'] before the helper. If a nominal-schema mocked report contains resource_limits=null/list/string rather than a dictionary, this raises TypeError rather than returning structured missing/invalid evidence. It still fails closed and cannot claim success. The assignment predates this correction, the trusted worker emits a dictionary, and no change is required to remedy the observed overage. A future parser hardening change could normalize/reject the type explicitly and add a mocked integration test.

## Evidence files
- freeze-check.json: initial individual expected/actual hash comparisons.
- selected-tests.txt: full selected test output.
- archived-reclassified.json: direct corrected archived report.
- additional-pure-classification-checks.json: extra rejection cases and malformed launcher result.

The parent is separately adjusting only evaluator failure wording and will provide an updated script freeze hash for a final delta check. This review does not approve an uninspected wording delta in advance.

## Final reviewed delta (supersedes pending-delta and hardening caveat above)
The parent made a minimal correction to preserve malformed resource_limits evidence and let the helper reject it instead of raising TypeError. I inspected that change and the new mocked None/list/string regression test. The evaluator now describes a nominal resource rejection as an overall regression expectation mismatch, including physical/budget flags and violations, rather than incorrectly calling it a six-step classification defect. Its acceptance conditions remain unchanged.

The complete refreshed 17-file corrective manifest matches (final-freeze-check.json). The final API SHA-256 is ca98ed0e61f97b263160fd50639472b1965cb7f46d6bc1412eba1d82bd5a190d; evaluator is 9ef40af59d89430593bfcf6fbd1528c61787113016efdc47f0638afaca34727d; tests are 90e3e55d776259d6a34e0ddd257ac74d79a89914067977fd334e51e35989d83b. Helper, worker, controller and physical implementation remain unchanged from the initial review freeze.

I reran only the same selected nonphysics modules/classes: all 17 tests passed in 0.131 seconds (final-selected-tests.txt). No blocking issue remains. Earlier TypeError evidence documents the intermediate state only and is resolved by this final delta. The archived classification and accounting limitations above remain applicable.
