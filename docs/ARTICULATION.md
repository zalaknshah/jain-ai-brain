# Original fixed-base articulated fixture

This is a real MuJoCo integration using an original, deliberately simplified humanoid-shaped model under this repository's MIT license. It includes a torso, head, two arms and two legs with nine actuated hinge joints. The pelvis is fixed to the world. The visual floor supplies no support/contact forces. It is an articulation/holding test bench, **not locomotion, standing balance, perception, hardware safety or full humanoid qualification**.

No external robot model, mesh, controller weights or sacred text is included. MuJoCo is the same optional Apache-2.0 backend documented in [SIMULATION.md](SIMULATION.md). The source asset is `src/jace/data/articulated_scene.xml`; reports record its SHA-256 and the actual backend version. Only that packaged XML is loaded by the interface.

## Run

After installing the optional simulation environment:

```sh
python -m jace.cli simulate-articulation --scenario clear_path --steps 1000 --confirm-simulation
python -m jace.cli simulate-articulation --scenario unavoidable_overlap --confirm-simulation
python scripts/evaluate_articulation.py
```

Without `--confirm-simulation`, the neutral posture is held and no posture transition is requested. This is simulation-only consent; policy outputs retain `executable=False` and `requires_confirmation=True`. No hardware, ROS publisher, external XML loader, network service or GUI path is exposed.

## Actual dynamics and guardrails

- Nine hinges use explicit radian ranges under ordinary downward gravity. Position actuators have a ±15 N·m actuator-force cap with unit hinge transmission; this does not bound all passive, contact or root reaction forces.
- The test transition flexes the left shoulder/elbow toward 0.55/0.65 rad. Other targets remain neutral. Normal target progression is limited to 0.2 rad/s, or 0.1 rad/s for the slow policy state. Linear policy velocity hints are not incorrectly treated as angular commands.
- Clearance is measured from every modeled robot geom to the synthetic obstacle and capped at the four-metre sensor range. Labels such as “living” are known fixture annotations, not detection or inference.
- Sensor loss, uncertainty, a policy halt, invalid commands or a fixture clearance reserve latch a hold state for the remainder of the episode. Recovery does not automatically restart motion. A new simulated episode is required.
- On the first halt, the controller captures the current posture rather than chasing the old goal. This emergency setpoint change is not governed by the normal progression rate. The actuators remain force-limited, and actual joint velocities/contacts are measured; holding is not instantaneous stopping or zero torque.
- The clearance latch threshold is 0.55 m for this fixture. Actual static-obstacle minimum clearance was approximately 0.549 m due to dynamics, above the tested 0.5 m reserve. Neither value is a general robot safety guarantee.
- Nonfinite values fail the run. Detected contact, excessive measured joint rate or joint-range violation ends the run with an explicit terminal reason. A 2,000-step limit bounds runtime/trace size. Early termination does not mean the mechanism has physically settled.

MuJoCo's normal connected-link filtering applies. Three explicit exclusions cover adjacent fixed-root head/hip contours that overlap at their connections. Nonadjacent self-contact and obstacle contact are still reported and are tested using deliberately colliding fixtures. “No contact” means no contact among the modeled enabled pairs, not proof that all real-body contacts are impossible.

## Evidence and adversarial checks

Six limited cases exercise clear motion, a static obstacle, a labeled living obstacle, scripted intrusion, sensor dropout and uncertainty. They check measured joint movement, a settled hold within the horizon, actuator limits and modeled clearance/contact bounds. Typical five-second clear-path endpoints are approximately 0.529 rad at the shoulder and 0.642 rad at the elbow, rather than pretending the servo perfectly reaches its targets.

The seventh case teleports an obstacle into the hand's occupied space. It is intentionally unavoidable and **must report contact**, terminate early and show negative clearance. Passing that test means honest failure detection, not collision avoidance. Separate regressions inject a nonadjacent self-collision, a nonfinite individual link measurement, invalid policy output and a transient halt followed by apparently clear data.

The tests do not validate articulated locomotion, free-base stability, realistic mass/inertia, real sensors, human/animal safety, contact-force acceptability, gait generation or physical robot control. Those require a separately chosen and validated robot/controller stack and broader engineering review.

## Cartesian hand targets

The `simulate-reach` command adds task-space input for the left hand rather than a single hard-coded posture. Coordinates are the **hand geom centre in the fixture's world frame, in metres**. The arm has only two planar joints: its shoulder is at `(0, 0.22, 1.4)` and link lengths are 0.28 and 0.25 m. Accepted goals must lie at `y = 0.22`, be geometrically reachable and admit a solution inside the shoulder/elbow limits. Invalid, nonfinite, out-of-plane, unreachable or joint-limit-incompatible input is rejected; it is not silently replaced with a reachable goal.

```sh
# Preview only: actual forward kinematics, no dynamics steps or actuation.
python -m jace.cli simulate-reach --target 0.3793621956 0.22 1.0707036952 --plan-only
# A separate explicit choice allows this bounded simulated episode.
python -m jace.cli simulate-reach --target 0.3793621956 0.22 1.0707036952 --confirm-simulation
python scripts/evaluate_reaching.py
```

The analytic inverse-kinematics solution is checked against actual MuJoCo forward kinematics, the packaged joint/actuator limits and the asset hash. Planning is **endpoint geometry only**. It does not establish a collision-free path, account for gravity tracking error, authorize motion, or prove a real robot can reach. Only the packaged original asset can be loaded. There is no arbitrary XML, natural-language action execution, grasping or hardware endpoint.

Execution passes the computed joint goal through the same rate-limited, force-capped, consent-gated controller and latched stop rules described above. `--scenario` can exercise the existing obstacle, uncertainty, dropout and expected-contact cases. `--steps` remains bounded to 1–2,000. Without simulation confirmation, the neutral posture is held. `--plan-only` never executes dynamics, even if confirmation is also present.

The report separates exact kinematic residual from **measured final endpoint error under dynamics**. `target_reached` requires confirmation, no latched stop or abnormal termination, no modeled contact, final hand-centre error at most 0.02 m and every final joint speed at most 0.02 rad/s. These are explicit fixture acceptance criteria, not exact positioning or a physical safety guarantee. A target already near the neutral hand still does not count as a confirmed reach without consent. A short horizon or safety hold is not mislabeled success.

Four exercised reachable targets finish approximately 4.3–13.1 mm from their requested endpoints under gravity. These small residuals are reported rather than replaced with the ideal inverse-kinematics answer. The evaluation also requires eight non-success outcomes (including the deliberately colliding scene) and rejects three impossible goals. Unit tests cover 35 forward/inverse boundary combinations, numerical straight-arm singularities, asset geometry/limit drift, nonfinite kinematics, consent and CLI preview/run behavior. This remains a fixed-base, two-joint task-space example, not general manipulation or humanoid qualification.
