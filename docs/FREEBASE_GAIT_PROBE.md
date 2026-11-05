# Experimental two-step free-base simulation

This is a separate experimental controller, not an extension of the frozen posture-controller gains. In the pinned simulation it performs a left step followed by a right step, then recovers double support. **It does not qualify sustained walking, general balance, hardware or physical safety.**

The nominal eight-second run measures:

- Left/right foot-body forward placement of 0.04022/0.08007 m relative to their initial world coordinates.
- Lowest foot-capsule clearance of 0.03695/0.03777 m during the respective swings, with observed airborne intervals, alternating loaded single support and subsequent contact.
- Net pelvis advance of 0.03503 m from the initial world position.
- Maximum root tilt of 0.02085 rad and a 1.524-second settled tail under the existing velocity/tilt criteria.

These are actual MuJoCo state/contact measurements, not commanded targets, root teleports or a posture animation. Contact re-lifting and chatter remain around transfers/landings. The nominal report includes 34 left-foot and 31 right-foot airborne observations outside their designated swing phases. These are sampled observations at 0.004 s, not unique incidents. No smooth or sustained gait is claimed.

## Run

Use **Python 3.12+** on Linux/POSIX with the separate optional `gait` extra. The qualified numerical stack is MuJoCo 3.17.0 and NumPy 2.5.4. NumPy 2.5.4 itself requires Python 3.12+. For an environment you manage, the installation command is `python -m pip install '.[gait]'`; no installation is performed by the probe.

The existing `simulation` extra remains `mujoco==3.17.0`, restoring its earlier Python 3.10/3.11 dependency declarations for the existing simulation features. Installing `simulation` alone does not select the exact qualified gait stack. The gait public API rejects unsupported Python, missing dependencies and different numerical versions before starting its worker. The worker repeats preflight and checks the loaded backend versions before creating a model. It never substitutes an unqualified NumPy version.

Run:

```sh
python -m jace.cli probe-gait --confirm-simulation
python -m jace.cli probe-gait --scenario small_lateral_first_swing --confirm-simulation --trace
python -m jace.cli probe-gait --scenario strong_forward_first_swing --confirm-simulation
python scripts/evaluate_gait_probe.py --confirm-simulation
python -m unittest discover -s tests -p 'test_freebase*.py' -v
```

Without explicit simulation confirmation, no physics worker starts. The only inputs are fixed scenario names, a 1–2,000-step budget and a trace choice. There is no arbitrary gain, model, script, weight, terrain, robot or URL input. `simulate-balance` and `diagnose-freebase` retain their original controllers and meanings.

Each run uses the same 1 GiB address-space, 15 CPU-second, 30 outer-wall-second limits, stripped environment and single numerical-library thread. Resource failures and worker errors are not successes or automatically retried. The separate `gait` extra matches the already installed and recorded `numpy==2.5.4` snapshot; MuJoCo remains `3.17.0`. No SciPy, new installation, GPU, network operation, provider or hardware was used. Resource caps are not a general sandbox for arbitrary executable models.

## Controller and unchanged model

The licensed, hash-checked modified Menagerie G1 remains unchanged: 29 actuators, free root, source inertias, gravity, timestep, control ranges, actuator-force caps, contacts and collision geometry. All licence notices remain. The earlier posture controller is byte-identical.

The prototype uses exact simulator state and model dynamics. It optimizes joint acceleration and hypothetical contact wrenches using center-of-mass, pelvis orientation, joint posture and foot-position/orientation tasks. It has a bounded active-constraint search with torque limits, nonnegative predicted normal forces and approximate friction/contact-moment bounds. This is a bounded feasibility heuristic, not a certified optimal QP solver. A nonfinite or infeasible final solution stops before another physics step. The predicted wrenches are **never applied as external forces**. Only source-bounded actuator position targets are written.

A contact-gated phase sequence prepares a slightly crouched posture, transfers toward the right foot, swings the left foot, transfers toward the left, swings the right, and recovers. Arm posture is commanded to provide modeled clearance. A swing touchdown gate above 0.5 N indicates detected contact, not weight-bearing support; later transfer criteria and measured support intervals distinguish these. No root constraint, root-state reset, hidden support or collision exclusion is added. No safety guard is relaxed.

The original height, tilt, actual joint-speed, actuator-force, nonfinite-state, quaternion, modeled unexpected-contact, sensor-dropout, numerical-warning and time-reset guards remain. `controller_feasibility_guard_triggered` additionally reports failure to find an acceptable control solution. The source soft joint limits/control clipping are not a proof of actual joint-position bounds. Contact-force acceptability and all real-body collision possibilities remain unqualified.

## Report meanings

`locomotion_controller: true` means this experimental controller exists. Its status is `experimental_two_step_only`; `walking_verified`, `balance_qualified`, `standing_verified`, `pretrained_policy_loaded` and `hardware_enabled` remain false.

`two_step_probe_accepted` requires:

1. All 2,000 steps, no guard stop, and at least one final uninterrupted second with root speed below 0.05 m/s, root angular speed and every joint speed below 0.1 rad/s, and tilt below 0.1 rad.
2. The exact phase sequence and chronological right-only then left-only loaded support lasting at least 0.1 s each. The supporting foot must carry more than 50 N and the other foot have zero modeled floor contacts.
3. Both feet clearing the floor by at least 0.01 m and subsequently making contact; left/right forward placement of at least 0.03/0.06 m; pelvis advance at least 0.025 m; lateral pelvis drift at most 0.03 m.
4. Both feet in contact and carrying more than 20 N each throughout the final second.

These are explicit narrow fixture criteria, not a walking certificate. `two_step_sequence_observed` can describe measured motion even when a later guard fails, while acceptance remains false. Short horizons cannot pass. Reports retain all airborne intervals, phases, predicted-solver residuals, measured support forces and source hashes. `--trace` includes observations before each executed command and an explicit final post-step snapshot at 8.000 s for a full run.

## Independent evidence and failures

An independent review froze the development candidate before selecting five unseen 0.1 s directional pulses: 12 N forward, 12 N backward, 12 N lateral, 25 N reverse lateral, and (25, 25, 0) N diagonal. The baseline plus all five completed the eight-second two-step checks. The historically named `medium_reverse_lateral_transfer` pulse actually occurs in right swing; its force/time definition is preserved and the observed phase is authoritative.

A 300 N forward pulse for 0.2 s during first swing **fails at 2.648 s on the pelvis-height guard**. This is an early termination, not observation of a completed fall. Initial 0.8 rad tilt fails before step 1; sensor loss fails at 0.4 s without another step. The original 100 N forward/lateral diagnostic pulses occur earlier, at 0.4–0.5 s during preparation, and complete this candidate's two-step horizon. They are not evidence for arbitrary 100 N pushes during walking.

The packaged implementation reproduces every compared control-trace field and dynamic metric of the frozen candidate and its independent scenarios. A separate injected controller-feasibility failure after one genuine step stops at exactly that step, without acceptance. `evals/gait/` records definitions, outcomes, reviews and development failures. Once used to change a future controller, these cases are regression tests, not new heldout validation.

The exploratory history includes unsuccessful open-loop transfers, self-contact, posture/joint-rate failures, a one-step-only horizon and an earlier incomplete constraint-search solver. These failures are retained rather than relabeled as walking. The final implementation stops on controller infeasibility rather than applying those failed solver outputs.

## Remaining work

This is one two-step sequence from one home state on one modeled flat floor. There is no cyclic walking command, navigation, terrain/friction generalization, robust contact handling, noisy/delayed sensing, physical calibration, general locomotion qualification or hardware connection. Contact chatter, stance-foot body motion and the approximate controller/soft-contact assumptions require further work and independent tests before broader claims. The numerical probe is meaningful progress toward humanoid locomotion, not completion of full humanoid qualification.
