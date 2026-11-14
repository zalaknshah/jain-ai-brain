JACE isolated gait revalidation 2026-11-14
Source main 20f0e1b4f628529fd4be3c0428801b28301269ad, unchanged code.
Python3.12.14 isolated venv; all10 PyPI wheel digests matched official release metadata, offline hash-locked install. MuJoCo3.17.0 NumPy2.5.4. All20 frozen implementation digests matched.
Single run frozen four-scenario evaluator exit0, all assertions passed. Nominal six steps accepted; initial tilt, sensor dropout, strong forward third swing rejected by expected guards. No rerun, cap modification, code change, or shared environment change.
Nominal final wait4 direct-child CPU6.373183s, outer wall6.40233420599543s, within15CPU/30wall caps. Pelvis advance0.1947829426938574m, settled tail4.028s.
This is simulated finite-horizon physics, not hardware/general walking/balance/resource reliability qualification. Earlier signal9 and archived CPU overrun remain evidence, not erased by this successful run. All hardware/walking/balance qualification flags false.
Independent audit passed without rerunning physics. Published evidence records one run only. CPU measurement covers the direct worker, not a descendant process tree; earlier failures remain unresolved.
