# Bounded free-base posture feedback experiment

This advances the [free-base diagnostic](FREEBASE_DIAGNOSTIC.md) from a neutral-servo fall to an original deterministic feedback controller. It is **not walking, full balance qualification, physical safety, or a learned policy**. No hardware endpoint is present.

On MuJoCo 3.17.0, the unchanged source neutral servo crosses its 0.5 rad tilt guard at 1.020 s. The new controller completes the existing maximum 2,000 steps (8 s), with maximum tilt 0.02118 rad and minimum pelvis height 0.78246 m. That is a measured finite-horizon improvement, not proof of indefinite stability.

## Run and inspect

Install the repository's optional pinned simulation environment, on Linux with POSIX resource limits, then:

```sh
python -m jace.cli simulate-balance --confirm-simulation
python -m jace.cli simulate-balance --scenario diagonal_push --confirm-simulation --trace
python -m jace.cli simulate-balance --scenario forward_push --confirm-simulation
python scripts/evaluate_balance.py
python scripts/evaluate_balance_heldout.py --confirm-simulation
python -m unittest discover -s tests -p 'test_freebase*.py' -v
```

Invoking the development evaluation script, or explicitly confirming the heldout evaluation, runs local numerical simulation; it does not authorize hardware. The application command requires `--confirm-simulation`. Without it, no worker or physics starts. The step budget is 1–2,000, including for private worker validation. A shorter horizon is never accepted as the eight-second experiment.

The entry point uses the same stripped subprocess environment and 1 GiB address-space, 15-second CPU and 30-second outer wall caps as the diagnostic. There are no network operations, external model paths, downloads, executable weights, GPU requirements or paid providers. These caps are not a general security sandbox. Worker errors, invalid reports and timeouts remain errors and are not retried.

## What the controller changes

The BSD-3-Clause modified Menagerie G1, its model hashes, body masses/inertias, free root, gravity, source actuator parameters/limits, contacts and collision geometry are unchanged. The source licence and provenance are retained. The controller is original repository code, not imported or pretrained code.

`g1-posture-feedback-v1` only returns 29 actuator position targets. It never assigns the root pose/velocity during the episode, freezes the base, adds support, changes physics or injects balancing forces. The only external forces are the disclosed test disturbances on the pelvis.

- The twelve leg joints use proportional/derivative joint feedback with gains 200 and 10. Other joints retain source gains.
- Both ankle pitch targets add 0.5 times root pitch plus 0.1 times root pitch rate. Both ankle roll targets use the corresponding roll values.
- Desired torques are converted into position commands using the unchanged source actuator gains and damping. Commands are clipped to the source control ranges; the source actuator force caps still apply.
- Reports count clipped command observations and maximum command changes. No command slew limit is claimed. Measured joint velocity remains guarded at 20 rad/s.

This uses exact simulator state, not validated sensors or perception. It is a local posture controller around the packaged home frame, not a general yaw-invariant control law. Joint-rate, actuator-force, height, tilt, nonfinite-state, invalid-quaternion, MuJoCo bad-state/control numerical-warning, simulation-time-reset, self-contact and non-foot floor-contact guards remain enabled. State is checked before the first step and after every subsequent step. Scripted sensor loss stops before another step.

`finite_horizon_posture_accepted` requires all 2,000 steps, no guard stop, and at least one uninterrupted final second with root linear speed below 0.05 m/s, root angular speed below 0.1 rad/s, all joint speeds below 0.1 rad/s, and tilt below 0.1 rad. `standing_verified`, `balance_qualified`, `walking_verified`, `locomotion_controller`, `pretrained_policy_loaded` and `hardware_enabled` remain false. A terminal guard stops numerical integration; it is not a physical emergency stop or evidence that a fall has settled.

## Development cases and retained failures

These cases were used during development and are not heldout evidence. All forces are world-frame pelvis forces; intervals are step indices at 0.004 s per step.

| Case | Disturbance | Outcome | Maximum tilt |
| --- | --- | --- | --- |
| Neutral | None | Full 8 s; settled tail 7.556 s | 0.02118 rad |
| Backward | (-60, 0, 0) N, steps 200–224 | Full 8 s; settled tail 6.544 s | 0.02951 rad |
| Diagonal | (45, 45, 0) N, steps 200–224 | Full 8 s; settled tail 6.056 s | 0.05848 rad |
| Reverse lateral | (0, -60, 0) N, steps 300–324 | Full 8 s; settled tail 5.596 s | 0.02118 rad |
| Original forward | (100, 0, 0) N, steps 100–124 | **Posture failure at 1.464 s** | 0.50016 rad |
| Original lateral | (0, 100, 0) N, steps 100–124 | **Unexpected contact at 0.576 s** | 0.01760 rad |
| Initial bad posture | 0.8 rad initial pitch | **Posture failure before first step** | 0.8 rad |
| Sensor dropout | Missing observation at step 100 | **Sensor guard at 0.4 s** | 0.00869 rad |

`evaluate_balance.py` checks both the four accepted finite-horizon cases and four reported failures. Passing these regression assertions does not turn failure scenarios into successful robot behavior. It also reruns the original neutral-servo baseline, which remains available unchanged through `diagnose-freebase`.

## Independent, frozen-controller perturbations

After freezing the controller file, an independent review selected eight previously untried force/time combinations, with no gain changes after selection. Their definitions, reproducible capped runner, summary and source hashes accompany `scripts/evaluate_balance_heldout.py` and `evals/balance/`. They are heldout relative to this controller development only; once checked in, future reuse is ordinary regression evidence.

Six new modest directional/timing perturbations complete the 8 s horizon and meet the same settled-tail criterion. Two stronger probes explicitly fail: a (150, -150, 0) N push over steps 500–539 causes self-contact at 2.156 s; a (-180, 0, 0) N push over steps 800–849 crosses the posture guard at 3.704 s. The review does not establish broad robustness, statistical generalization or physical transfer.

## What remains

There is no gait generator, stepping strategy, support switching, foot-placement planner, terrain handling or locomotion command. Known 100 N failures and limited model contact coverage remain. Walking was not attempted by disguising joint motion or root displacement as a gait. It needs a compatible controller with separately measured foot lift, alternating support, intentional translation, recovery/fall behavior and independent terrain/perturbation tests. Real sensing, secure evaluation of any future learned policy, contact-force acceptability, broader model validation and physical hardware qualification are separate unresolved work.
