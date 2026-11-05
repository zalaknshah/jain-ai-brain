# Experimental six-step free-base simulation

This separate, original experiment extends the contact/CoM prototype to **one continuous 20-second episode with six alternating steps**, then double-support recovery. It is a measured finite-horizon simulation result, **not general walking, balance, standing or hardware qualification**. The earlier posture, diagnostic and two-step controllers and their 2,000-step maximum are unchanged.

**Resource/process reliability remains unresolved:** one nominal worker was killed with signal 9 during testing. A later installed-package run physically completed all six steps but reported 15.80148 CPU seconds against the 15-second budget. The original report incorrectly returned acceptance; the separate resource-verdict correction rejects that archived overage without changing its physical measurements. Neither later physical completion nor the correction resolves execution reliability.

## Nominal development result

The frozen controller completes six actual left/right foot swings, not six replays or resets. Each step has 0.544–0.548 s of measured opposite-foot support above 50 N while the swing foot has zero modeled floor contacts. Actual lowest foot-capsule clearances are 0.03648–0.03748 m. Foot-body advance is 0.04022 m on the first step and 0.08054–0.08078 m on subsequent steps. Every landing is followed by a measured loaded-contact interval. Net pelvis advance is 0.19478 m, maximum root tilt is 0.02041 rad and the final uninterrupted settled tail lasts 4.028 s.

Contact chatter remains. The initial six-step development extension had 160/155 left/right airborne observations outside the respective planned swing phases. At 0.004 s per sample these represent 0.640/0.620 s, or 3.617%/3.508% of eligible non-swing time. The selected contact-tuned development candidate has 42/43 such samples: 0.168/0.172 s over 17.828/17.864 eligible seconds, or **0.942%/0.963%**. These are sampled contact states, not unique incidents, and these percentages are nominal development measurements, not independent heldout performance. Reports also retain a chronological breakdown for every transfer/swing/recovery phase so a longer settled tail cannot hide where chatter occurs.

The controller moves the transfer CoM target 0.015 m inward from the support-foot body center and commands the swing endpoint 0.001 m below the initial foot-body height to maintain contact. These are actuator-generated tracking targets; the floor, foot geometry, contact solver, friction, gravity and model are not changed. Five nominal development variants and the worse-chatter 0.020 m inset trial remain in `evals/sustained_gait/development_history.json`. The final endpoint trajectory includes its three-axis interpolation velocity and acceleration.

## Run

Use Linux/POSIX and the already-qualified Python 3.12+ `gait` extra: MuJoCo 3.17.0 and NumPy 2.5.4. No install happens in the experiment.

```sh
python scripts/probe_sustained_gait.py --confirm-simulation
python scripts/probe_sustained_gait.py --confirm-simulation --trace
python scripts/probe_sustained_gait.py --scenario strong_forward_third_swing --confirm-simulation
python scripts/evaluate_sustained_gait.py --confirm-simulation
python -m unittest discover -s tests -p 'test_freebase*.py' -v
```

The standalone script/API accepts only fixed scenario names, an integer 1–5,000-step budget and a trace choice. Explicit simulation confirmation is required before physics. There is no user-supplied model, gain, policy, terrain, endpoint or executable input. Only this lane permits 5,000 steps; old APIs still reject budgets above 2,000.

The worker retains **1 GiB address space, 15 CPU seconds and 30 outer wall seconds**, plus a 1 MiB file-size limit and one numerical-library thread. The environment is stripped; arbitrary executable model sandboxing is not claimed. Worker CPU/wall time, outer time, peak RSS and configured limits are reported. Limits are operating-system ceilings with enforcement granularity, not a guarantee that resource usage counters will end below an exact fractional-second boundary. A killed/timeout/error worker is an explicit failure and is never automatically retried or counted as a successful episode. Measured timings vary with host load.

## Exact narrow acceptance

`physical_six_step_criteria_met` describes only the following physical criteria:

1. All 5,000 steps in one continuous episode, no physical/numerical/feasibility guard stop, and at least one final uninterrupted second with root speed below 0.05 m/s, angular and every joint speed below 0.1 rad/s, and tilt below 0.1 rad.
2. Exactly six alternating swings in the specified contact-gated phase order. For **each** step, actual opposite-foot floor support above 50 N while the swing foot has zero contacts must persist for at least 0.1 s. Actual airborne capsule clearance must reach 0.01 m, followed by contact above 0.5 N and at least 0.1 s of subsequent landing-foot contact above 50 N.
3. Per-step actual foot-body forward motion of at least 0.03 m on the first step and 0.06 m on every later step. Final pelvis advance of at least 0.17 m and **final** lateral displacement at most 0.03 m. The lateral threshold does not limit the substantial side-to-side excursion during transfers.
4. Both feet in floor contact and each carrying more than 20 N throughout the final second.

`sustained_probe_accepted` now additionally requires `observed_resource_budget_satisfied`: cumulative reported worker CPU must be at most 15 seconds and observed worker wall time at most 30 seconds; the launcher also checks its measured outer elapsed time against 30 seconds. Missing, nonfinite, negative or incorrectly typed counters, or missing/changed configured caps, reject acceptance. There is no overrun tolerance for classification. A resource overage leaves physical metrics, physical terminal reason and physical criteria flags intact while setting overall acceptance false and listing `resource_budget_violations`.

CPU accounting is cumulative `RUSAGE_SELF` for this worker process, including interpreter startup, imports, model setup, simulation and report construction. It does not include the parent/sibling processes and is not startup-subtracted. Its sample is taken before the final verdict, JSON serialization/output and process exit, so it is a **lower bound on final worker CPU, not proof of lifetime compliance**. The `_run` wall timer begins later than process startup; the launcher timer includes subprocess completion/response parsing but excludes its final verdict and caller work. `resource_verdict_stage` distinguishes the provisional worker report from launcher reassessment. `resource_accounting_scope` explicitly keeps full-lifetime CPU measurement and resource-reliability qualification false even for an accepted observed-budget result.

Support durations conservatively use elapsed time between qualifying observations. The trace contains pre-command observations at 0.004 s intervals and a separate final post-step snapshot. Chatter durations use each sample's interval to the next observation; the last snapshot contributes no duration. A phase command, sliding feet, total displacement or a short successful prefix alone cannot pass. Measurements can remain useful when final acceptance fails.

## Physical and implementation boundaries

The licensed, hash-verified modified Menagerie G1 retains its free root, 29 actuators, source inertias, force/control ranges, gravity, collision geometry, contacts and timestep. No root writes occur after initialization; no root constraint, reset between steps, invisible support, collision exclusion, force application from predicted contact wrenches or hardware connection is added. Only bounded actuator position targets drive the gait; externally applied forces are the explicitly documented test disturbances.

The bounded active-constraint feasibility heuristic, at most 64 iterations, retains torque and approximate friction/contact-moment constraints. Final nonfinite/infeasible solutions stop before another physics step. It is not a certified QP or whole-body contact solver. Source model checking and all existing height, tilt, actual joint-speed, actuator-force, nonfinite, quaternion, unexpected-contact, dropout, numerical-warning and clock-reset guards are preserved. Soft joint target limits do not certify actual joint-position bounds.

Exact simulator state/dynamics, one home state and one flat floor are used. The six-step plan is finite, slow and fixed; it is not a user-directed navigation command or unlimited stable limit cycle. Sensor noise/delay, floor/friction variation, real-body collision completeness, contact-force limits, physical calibration and robustness beyond the reported cases remain unqualified. `walking_verified`, `balance_qualified`, `standing_verified`, `pretrained_policy_loaded` and `hardware_enabled` remain false.

## Failures and independent review

A development 300 N forward pulse during the third swing (7.2–7.4 s) triggers the controller-feasibility guard at 7.528 s, after 1,882 steps. It is a failed episode, not a completed fall or six-step success. The 0.8 rad initial tilt stops before step 1; sensor loss stops at 0.4 s without another step.

After freezing all source hashes, an independent reviewer selected four modest pulses: +12 N forward at 8.4–8.5 s, −10 N forward at 10.4–10.48 s, +8 N lateral at 12.0–12.1 s and (8, −6, 0) N diagonal at 14.0–14.08 s. Nominal plus all four passed independently recomputed per-step criteria, with 0.19442–0.19502 m advance and over four seconds of settled tail. Nominal full physical/control traces repeated exactly. Actual phases are recorded separately because some preregistered case names do not match their observed phases. Independent chatter spans 0.829–1.030% of eligible non-swing time, so no claim that every case is below 1% is made.

An independently chosen 250 N lateral pulse at 11.2–11.4 s fails on modeled self-contact at 11.416 s after 2,854 steps. Only four swings completed. Its reported CPU usage is 15.113889 s with the configured Linux 15-second limit; operating-system enforcement did not prevent that observed overage. It is a failed run, not a qualifying one. The correction also labels this observed CPU budget violation. Successful independent episodes used 8.15–10.59 CPU seconds and 8.63–11.29 outer wall seconds. Maximum reported RSS across review episodes was 121,272 KiB; inherited high-water marks can affect this measurement.

The reviewer independently recomputed metrics from raw state/contact traces and checked the source capsule-clearance formula, but did not reconstruct clearance from full geometry transforms because those transforms are not stored in the trace. The maximum nominal lateral excursion is 0.12681 m, much larger than its −0.00175 m final lateral displacement.

One nominal trace worker in the first focused test run exited with signal 9 and no stderr. Its cause was not established; it was correctly rejected as a process failure. The code path shows this was a returned signal-9 termination, not the API’s outer-timeout exception. The focused suite overlapped the independent reviewer’s runs; causation is not established. Per-worker elapsed/CPU measurements were unavailable because it produced no report. Resource/process reliability remains unresolved despite later successful runs. See `evals/sustained_gait/` for the frozen source manifest, independently registered perturbations, measured outcomes, full regression comparisons and resource/process failures. Previously unseen cases are heldout only relative to this frozen development cycle; future use makes them regression cases. A finite set of successful perturbations cannot establish general robustness.

## Resource-verdict correction evidence

The original `f8a86ed` results and freeze manifest are preserved unchanged. Its outside-checkout installed nominal report records 5,000 steps, 0.1947829427 m advance, 15.80148 cumulative CPU seconds and 25.074059 outer wall seconds while `sustained_probe_accepted` was true. Source inspection established that acceptance had been calculated before usage sampling and never checked the counters. The corrected classification retains `physical_six_step_criteria_met: true`, sets `observed_resource_budget_satisfied: false` and `sustained_probe_accepted: false`, and records the CPU overage. This is a deterministic reclassification of archived data, not a new successful simulation.

`evals/sustained_gait/resource_verdict_freeze.json` binds the corrective source state; `candidate_freeze.json` continues to bind the historical physical candidate. The corrected evaluator checks the corrective manifest. Deterministic source/contract checks and archived-report classification are reported separately from actual physics/performance runs. No controller, model, resource limit, historical failure or performance test was changed to obtain the correction.
