# Fresh private-study package integration

At the API-only checkpoint 6f81e7c, this separately named API packaged the reviewed standalone fresh-v1 consumer
inside JACE. It did not replace `jace.private_study`, change legacy pins, convert
fresh records into the legacy schema, or connect study results to the engine,
CLI, browser, model training or robot decisions at that checkpoint.

Import `ExpectedPins`, `StudyDeclaration`, `ConsumerError`, and `consume` from
`jace.fresh_private_study`. Every invocation requires independently trusted six
SHA-256 pins and the exact source/version/license/private-purpose opt-in. Pins
must not be derived from the candidate bundle. No source path is defaulted.
The underlying consumer verifies the complete bundle on every call. Its default
is metadata-only inventory; lookup returns separate original parsed records in
memory, retaining attribution and notices. Noncandidate disclosure still needs
separate explicit review opt-in; that opt-in does not mean scholarly validation.

Callers must not print or transmit real return values or exception locals without
separate appropriate authorization. No corpus is included. All rights, source
validation, translation, runtime and training admission gates remain unchanged.
That checkpoint was a Python API integration, not a user-facing study experience.
The subsequent explicit local CLI is documented in fresh-source-study-cli.md;
it adds no engine, web, model-training or robot-decision linkage.

Implementation lineage:
- Standalone consumer checkpoint 85f39f0, consumer SHA-256
  24b34c2f2b00a5818e72d2a99109aef63933ebf50f7312e5cb52c1e91ab33cb2.
  Only its preparation import becomes package-relative.
- Frozen preparation checkpoint 45fa7f0bf361ad7955634e3f9dea8464903cee26,
  SHA-256 f833d8ed0895567f7f708abb4b11ca27e01c33a628d9b6e3da32e1c06862431f,
  byte-identical in this package.
- Integration tested against local JACE baseline
  4991a55ed1029184f2798aa27734f656764cd845, not an asserted current-main merge.

Observed local tests: 53 fresh preparation/consumer/API tests and 33 unchanged
legacy private-study tests passed. All fixtures are invented. No real private
corpus, model, service, Windows qualification or full application test was run.

From a complete checkout after applying the additive files:

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -p 'test_fresh_package_*.py' -v
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -p '*private_study*' -v

The consumer uses POSIX descriptor-relative IO and private owned file modes.
Windows support is not claimed. Do not add an unsafe fallback for unsupported
platforms. Existing held corpus publications and translations are unaffected.

## Main integration check, 14 November 2026

Rebuilt the candidate from current public main
`aba465eedfa95974164532ed52eaf9103787d12f` plus the eight feature files.
The first full suite ran 888 tests with 54 skips and one failure: the exact
Docker context allowlist omitted the new package. Added only four exact Python
file exceptions and corresponding explicit container regression expectations;
private source descendants remain excluded. The corrected full documented
unittest suite ran 888 tests in 69.362 seconds: OK, 54 optional skips.
Independent review reran all five static container checks and reviewed the
exact source-only diff. Package discovery and syntax checks also passed.

This is not a Docker build/run qualification; no image, service, real source
bundle, robot, trained model or Windows test was run. No GitHub CI check runs
were present on the feature commit at inspection. The prior failed run is not
counted as a pass. Legacy private-study code and pins remain byte-identical to
main. No held evaluator or split-guard feature is included in this integration.

The subsequent literal-search extension is described in fresh-literal-search.md.
It adds an explicit search operation without changing preparation bytes or
legacy pins. The import-only consumer diff above describes the API-only milestone,
not the later search extension.
