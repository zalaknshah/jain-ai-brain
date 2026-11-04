# Optional real-physics fixture

JACE now connects its high-level motion policy to an actual MuJoCo CPU simulation. This is an original one-axis sphere/slider scene, not a humanoid, gait controller, vision system or physical robot integration. No hardware publisher, network endpoint, rendering window, model download or caller-supplied XML loader is exposed by this adapter.

## Run locally

The base package remains dependency-free. For the optional backend, create an isolated environment and install the simulation extra:

```sh
python -m venv .venv-simulation
# Activate that environment, then:
python -m pip install '.[simulation]'
python -m jace.cli simulate-physics --scenario static_obstacle --steps 1000 --confirm-simulation
python scripts/evaluate_physics.py
PYTHONPATH=src python -m unittest discover -s tests -v
```

MuJoCo 3.17.0 is pinned in the extra. `requirements/simulation-py312.txt` records the complete versions exercised with CPython 3.12 on Linux x86_64. It is a tested version snapshot, not a hash-verified lock or a claim that other Python/platform combinations were tested. The [official MuJoCo Python package](https://mujoco.readthedocs.io/en/stable/python.html) includes the simulation library. MuJoCo and its bindings use [Apache-2.0 licensing](https://pypi.org/project/mujoco/); the original scene in this repository uses the repository's MIT license. No third-party robot asset is included.

Without the optional dependency, the physics command exits with an error. Its tests are explicitly skipped in the base environment; a skipped test is not evidence that physics ran. The legacy `simulate` command still exercises only scalar policy cases.

## Closed-loop contract

- `mj_step` advances a dynamic slider with mass, damping and a bounded velocity actuator. No GUI or GPU is needed for these stepping tests.
- Before every step, `mj_geomDistance` measures signed sphere-to-sphere clearance, capped at a four-metre synthetic sensor range. Geometry and contacts are refreshed after integration.
- The existing policy proposes stop/slow/proceed. The simulation adapter limits the target to 0–0.25 m/s, rejects invalid policy commands and applies motion only when this episode has `confirm_simulation=True` / `--confirm-simulation`.
- The proposal still has `executable=False` and `requires_confirmation=True`. Simulation confirmation never authorizes physical motion.
- A separate two-centimetre clearance reserve handles residual braking travel in this fixed fixture. Without it, the first real-physics test crossed the nominal 0.5 m threshold by approximately 3 mm. With it, the static-obstacle case stopped at approximately 0.516 m clearance. This is fixture-specific evidence, not a general braking-distance guarantee.
- Missing/nonfinite state stops the run; sensor dropout produces a stop proposal. Runs have a hard 2,000-step budget and return measured state, clearance, contact count, control-stop reasons and the scene SHA-256. `--trace` includes bounded per-step records.

The six scenes are clear path, static obstacle, tagged living obstacle, scripted obstacle intrusion, sensor dropout and uncertain sensor. Living/fragile labels are synthetic annotations, not inferred from camera images. Intrusion is scripted scene motion. The floor is visual only; the slider is constrained to one axis. There is no balance, walking, articulated body, rerouting, learned policy, real sensing or energy-optimization proof.

## Verification boundary

The physics evaluation asserts movement in the clear fixture, settled stops in the other five fixtures, no obstacle contact and at least 0.5 m measured clearance. Unit tests additionally cover no-confirmation behavior, invalid policy output, nonfinite geometry and repeatability. These are small deterministic fixtures, not certification of a real robot or evidence of zero harm.

A real humanoid integration still requires a chosen licensed robot model, reviewed dynamics/controller limits, perception and uncertainty modelling, richer adversarial scenarios, emergency-stop design and separately authorized hardware work.

The later [fixed-base articulation fixture](ARTICULATION.md) adds nine hinged joints and gravity while explicitly leaving balance and locomotion unresolved. It uses the same optional backend and does not change the slider evidence above.
