# Two-step simulation evidence

See `docs/FREEBASE_GAIT_PROBE.md` for scope and exact acceptance criteria. These files describe simulation experiments, not walking/hardware qualification.

- `results.json`: all 11 public fixed scenarios, including eight accepted finite horizons and three explicit guard failures. Exact model/controller hashes, backend versions, limits, source licences and physical measurements accompany the reports.
- `independent_case_registration.json`: cases chosen after the original candidate was frozen. The candidate hash and original independent acceptance criteria are retained; packaged acceptance is stricter and all reviewed nonfailure cases meet both. The historical reverse-lateral case label is clarified without changing its force/time.
- `development_history.json`: every retained version 1–14 development trial, with failed outcomes, parameter choices and source hashes. These are development results, not heldout evidence or automatic walking successes. The final packaged controller preserves version 14 case 0 math. Large raw development traces remain separate from this compact published record.

Run `python scripts/evaluate_gait_probe.py --confirm-simulation` to reproduce the fixed outcomes. Five reviewer-selected pushes are heldout only relative to this frozen development cycle; future reuse is regression. Contact chatter remains and is visible in the reports. The original posture controller/model were not changed to obtain these results.

`reviewed_source_sha256.json` binds the reviewed bytes. `comparison.json` records exact frozen-to-packaged replay equality, `final_tail_checks.json` verifies the actual final-second samples, `regression.json` preserves eight existing-mode comparisons, and `fault.json` records the one-step feasibility-stop injection. These are technical verification artifacts, not hardware or general walking certification.

`runtime_compatibility.json` records the focused correction after commit 674230bb: the original MuJoCo-only simulation extra is restored, and the exact Python 3.12+ numerical stack is isolated in the gait extra. It includes offline generated package metadata, preflight checks and eleven unchanged qualified-runtime replays. Python 3.10/3.11 cases were synthetic, not installation tests; no packages were installed. The current reviewed-source hashes and validation totals include this correction.
