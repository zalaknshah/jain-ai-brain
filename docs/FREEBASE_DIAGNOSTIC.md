# Modified free-base G1 diagnostic

This diagnostic makes a remaining gap visible: the robot is no longer fixed to the world, and a neutral position-servo posture does **not** stay upright. In the tested fixture, it crosses a 0.5 rad tilt guard after about 1.02 simulated seconds. This is an expected failure result, not standing, gait, locomotion, validated balance, contact safety or physical robot qualification.

## Source, licence and exact modification

The source is the [Unitree G1 MJX variant in Google DeepMind MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie/tree/98a70c569c4c1b6da467a20012f766ee1f8dc521/unitree_g1), pinned at commit `98a70c569c4c1b6da467a20012f766ee1f8dc521`. The model's [BSD-3-Clause licence](https://github.com/google-deepmind/mujoco_menagerie/blob/98a70c569c4c1b6da467a20012f766ee1f8dc521/unitree_g1/LICENSE) permits modified redistribution with the notices retained. This third-party model is not relicensed under JACE's MIT licence. Source attribution is not endorsement.

- `third_party/unitree_g1/` retains the exact upstream XML, licence, Git blob IDs and SHA-256 hashes.
- `scripts/derive_headless_g1.py` reproducibly removes 35 zero-density visual mesh geoms and 35 mesh assets, the unused visual default and mesh-directory setting. It changes the scene's include filename and regenerates XML formatting.
- The derivative retains the source's 30 explicit body inertias, 29 actuated joints, free root, collision primitives, 49 contact pairs, position-actuator limits, solver settings and home keyframe.
- The packaged `unitree_g1_LICENSE.txt`, `unitree_g1_NOTICE.txt` and `unitree_g1_source.json` retain notices and provenance. Runtime verifies hashes of both fixed packaged XML files. It accepts no arbitrary model path or URL.

The source model already uses selected collision primitives and explicit contact pairs. Removing visual meshes is not a claim that the source geometry is physically validated, that every possible self-contact is modeled, or that this derivative has been qualified against a real G1. The upstream full visual model was not compiled successfully for numerical equivalence here; structural regressions verify the retained source parameters. No third-party robot mesh or pretrained controller is included in this package.

## Run

The optional pinned MuJoCo environment is required. This diagnostic additionally requires Linux/POSIX resource-limit support; it does not silently fall back to an unrestricted process on another platform.

```sh
python -m jace.cli diagnose-freebase --confirm-simulation
python -m jace.cli diagnose-freebase --scenario lateral_push --confirm-simulation --trace
python scripts/evaluate_freebase.py
```

Without explicit simulation confirmation, no worker or physics step starts. Each confirmed run launches a separate subprocess with a small, explicit environment, one numerical-library thread, a 1 GiB address-space limit, a 15-second CPU-time limit and an outer 30-second wall-time limit. A timeout or failed/killed worker is an error, never a success, and is not retried automatically. The fixed model used about 60–70 MiB peak RSS during the initial Linux tests. A clean environment and resource caps are **not a general security sandbox for executable model files**; no TorchScript or other learned policy is loaded.

Steps are limited to 1–2,000 at the source timestep of 0.004 s. Only the source home position targets are applied. There is no walking command, root balance feedback, learned controller, sensor/network service, ROS bridge, real credentials or hardware access.

## Outcomes and guards

The five fixed cases are:

1. Neutral posture: the source position servos become unstable and trigger the posture guard at approximately 1.02 s.
2. Forward push: a scripted 100 N force on the pelvis for 0.1 s tests the same diagnostic. This is an external simulation force, distinct from actuator torque limits.
3. Lateral push: the same lateral disturbance produces an unexpected modeled contact in the tested fixture, which is reported as failure.
4. Initial tilt: an already tilted starting state is rejected before the first physics step.
5. Sensor dropout: the run terminates before taking another step when the scripted observation disappears at 0.4 s.

State is checked before the first step and after each subsequent step. Nonfinite state or invalid orientation fails the run. Root height below 0.55 m, tilt above 0.5 rad, joint speed above 20 rad/s, force-limit violation, non-foot floor contact or a modeled self-contact terminates the diagnostic. The six source foot-floor collision shapes are expected support contacts; their presence is not mislabeled a collision failure. Contact counts are sampled contact observations, not unique collision incidents.

These are **termination criteria**, not a physical emergency stop: stopping the simulator does not show that a falling robot has settled or that contact was avoided. The report records actual completed steps, pose/tilt, source hashes and applied resource limits. `no_guard_triggered_within_horizon` only describes that finite horizon. Even a short run without a guard event always has `standing_verified: false`, `locomotion_controller: false` and `hardware_enabled: false`.

The evaluation passes only when the expected failures are reported honestly. A compatible balance/locomotion controller, secure execution of any external executable weights, broader perturbation/contact validation and real perception remain unresolved. The unrelated Unitree 12-joint pretrained policy was inspected statically but is not run or combined with this 29-joint model.
