# Frozen-controller simulation evidence

These are numerical MuJoCo 3.17.0 results from Linux, not safety certificates. All scenarios start from the one packaged G1 home state on its flat floor. Model source hashes/licensing and process limits are recorded in each report. Peak RSS is process-specific and is excluded from deterministic equality checks.

- `development_results.json`: original neutral-servo baseline, four accepted 8 s feedback posture experiments, and four explicit expected guard failures. These cases were used in development.
- `heldout_cases.json`: eight force/time definitions chosen independently after freezing controller SHA256 `2d0d9970b33c074ed1569a2c96bb0b8ff1ce1e0e5887bf80198b6b56ecc59726`. The exact file SHA256 is `a68d54c6331ee761ebf7bbb722200c73660f399562de86ea770f85912cef6646`.
- `heldout_results.json`: six accepted finite horizons and two explicit strong-push failures. Rerun using `python scripts/evaluate_balance_heldout.py --confirm-simulation`. These cases are ordinary regression evidence for any future controller changes, not reusable unseen validation.
- `reviewed_source_sha256.json` and `independent_verification.json`: exact reviewed source identity and exact dynamics replay verdict after adding numerical-warning/reset guards. No gain tuning occurred after heldout selection.
- `fault_injection_results.json`: five independent capped runs injecting one MuJoCo bad-state/control warning counter or a clock reset immediately after one genuine step. Every run stops at step 1 without acceptance. These inject signals rather than inducing actual numerical instability. Reproducible equivalents are included in `tests/test_freebase_balance.py`.

The accepted reviewed cases also had foot contact throughout their final second. Acceptance does not evaluate support-polygon margin, foot slip, actual joint-position bounds, noisy/delayed sensors, terrain/friction variation, arbitrary yaw/initial velocities, repeated disturbances or longer horizons. No walking, general balance, hardware, or contact-force acceptability is qualified. See `docs/FREEBASE_BALANCE.md` for controller behavior, assumptions and limitations.
