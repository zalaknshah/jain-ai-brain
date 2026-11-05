"""Original deterministic posture feedback for the packaged 29-joint G1 fixture.

Only actuator position targets are changed. No model edits, root constraints,
external support forces, inverse dynamics, learned weights or gait generation.
"""
from __future__ import annotations
import math


class PostureFeedback:
    def __init__(self, model, data):
        import numpy as np
        self.np = np
        self.home = data.ctrl.copy()
        self.gains = model.actuator_gainprm[:, 0].copy()
        self.kp = self.gains.copy()
        self.kd = np.full(model.nu, 2.0)
        # Only leg joints receive stronger explicit joint feedback. Upper-body
        # servos keep their source gains; strong explicit wrist damping is unstable.
        self.kp[:12] = 200.0
        self.kd[:12] = 10.0
        self.low = model.actuator_ctrlrange[:, 0].copy()
        self.high = model.actuator_ctrlrange[:, 1].copy()
        if (model.nu != 29 or not np.all(self.gains > 0)
                or not np.all(model.actuator_ctrllimited)
                or not np.array_equal(model.actuator_trnid[:, 0], np.arange(1, 30))
                or not np.all(model.actuator_gear[:, 0] == 1)):
            raise RuntimeError('unsupported posture feedback actuator mapping')
        self.clipped_target_observations = 0
        self.maximum_target_delta_rad = 0.0

    def command(self, data):
        np = self.np
        if not np.all(np.isfinite(np.r_[data.qpos, data.qvel])):
            raise RuntimeError('nonfinite posture feedback observation')
        w, x, y, z = (float(v) for v in data.qpos[3:7])
        vertical_z = 1 - 2 * (x*x + y*y)
        pitch = math.atan2(2 * (w*y - z*x), vertical_z)
        roll = math.atan2(2 * (w*x + y*z), vertical_z)
        target = self.home.copy()
        # Small-angle local posture feedback. This is not a global yaw-invariant
        # locomotion policy; the episode begins in the packaged home frame.
        target[[4, 10]] += .5 * pitch + .1 * float(data.qvel[4])
        target[[5, 11]] += .5 * roll + .1 * float(data.qvel[3])
        desired_torque = self.kp * (target - data.qpos[7:]) - self.kd * data.qvel[6:]
        # Retain source kp/kv, ctrl limits and force caps. Compensating source
        # damping converts desired torque into its permitted position target.
        raw = data.qpos[7:] + (desired_torque + 2 * data.qvel[6:]) / self.gains
        if not np.all(np.isfinite(raw)):
            raise RuntimeError('nonfinite posture feedback command')
        limited = np.clip(raw, self.low, self.high)
        self.clipped_target_observations += int(np.count_nonzero(raw != limited))
        self.maximum_target_delta_rad = max(self.maximum_target_delta_rad,
                                            float(np.max(np.abs(limited - data.ctrl))))
        return limited
