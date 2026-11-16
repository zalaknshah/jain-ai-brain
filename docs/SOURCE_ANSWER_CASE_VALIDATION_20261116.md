# Saved-answer case validation checkpoint

Base: `1013c4c3415b4d644dbbf2439c57358fea0ea26c` (GitHub main verified
2026-11-16). GitHub reported no open pull requests. Development used an isolated
checkout; existing JACE checkouts and Vectrelay processes were not modified.

Duplicate evidence IDs now invalidate a case before scoring. Previously they
could count as a rejected answer, or remain undetected with no saved answer.
Validation includes unreviewed records and both identical and conflicting
passages. IDs may still repeat across separate cases.

## Validation on Nrupay Windows / Python 3.10.4

- Saved-answer tests: 14 passed; one existing CLI test failed because the secure
  reader requires POSIX no-follow directory I/O. The same CLI test from base
  commit 1013c4c reproduces this failure. The reader and its gate are unchanged.
- The new duplicate-ID test first failed all 12 combinations before the fix,
  then passed. Two positive tests cover cross-case reuse and distinct IDs.
- Model-output tests: 15 passed with `PYTHONUTF8=1`. Without UTF-8 mode, an
  existing fixture-loading test fails under the Windows cp1252 default.
- Translation-review binding tests: 4 passed.
- `git diff --check` passed. No full suite, model or native runtime was run.

These are original synthetic regression fixtures only. They do not qualify a
model, native runtime, robot, scholarly interpretation or bilingual translation.
No private corpus was read or modified; no excerpts were approved for training.
Rights, review, training, runtime, publication and robot-control gates remain.
