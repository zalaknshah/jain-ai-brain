"""Original bounded six-step extension of the contact/CoM simulation prototype.

Only bounded actuator ctrl is returned. Optimization contact wrenches are never
applied to the simulator, nor is the free root constrained or overwritten.
This bounded feasibility heuristic is not an optimal-QP or walking certificate.
Separate development lane; the earlier two-step controller stays byte-identical.
"""
from __future__ import annotations
import math
import mujoco
import numpy as np
from .freebase_balance_controller import PostureFeedback
from .freebase_gait import ControllerFeasibilityError

CONFIG = {'root_kp': 80, 'joint_weight': .1, 'upper_weight': 1., 'drop': .025,
          'swing_s': .6, 'transfer_s': 1.6, 'recover_s': 1., 'settle_s': .4,
          'step_m': .04, 'moment_weight': .1, 'arm_roll': .8, 'arm_pitch': .2,
          'support_x_offset': .03, 'planned_steps': 6, 'support_inward_m': .015, 'landing_depth_m': .001}

def orientation_error(target, current):
    r = target @ current.T
    return 0.5 * np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])

def smooth(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * s * (10 + s * (-15 + 6 * s))

class SustainedGaitPrototype(PostureFeedback):

    def __init__(self, m, d):
        super().__init__(m, d)
        self.m = m
        self.qhome = d.qpos[7:].copy()
        self.qhome[16] = CONFIG['arm_roll']
        self.qhome[23] = -CONFIG['arm_roll']
        self.qhome[[15, 22]] = CONFIG['arm_pitch']
        self.comgoal = d.subtree_com[1].copy()
        self.com_initial = self.comgoal.copy()
        self.bodies = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, s + '_ankle_roll_link') for s in ('left', 'right')]
        self.footgoal = [d.xpos[b].copy() for b in self.bodies]
        self.foot_initial = np.array(self.footgoal)
        self.footrot = [d.xmat[b].reshape(3, 3).copy() for b in self.bodies]
        self.prev = {}
        self.phase = 'settle'
        self.start = 0.0
        self.events = []
        self.gate = 0
        self.completed_swings = 0
        self.swing_start = None
        self.swing_target = None
        self.transfer_start = self.comgoal.copy()
        self.controller_end = None
        self.control_trace = []
        self.initial_root = d.qpos[:3].copy()
        self.foot_geoms = [
            [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f'{side}_foot{i}_collision')
             for i in (1, 2, 3)] for side in ('left', 'right')]
        if any(m.geom_type[g] != mujoco.mjtGeom.mjGEOM_CAPSULE
               for group in self.foot_geoms for g in group):
            raise RuntimeError('unexpected gait probe foot collision geometry')

    def jac(self, d, body):
        jp = np.zeros((3, self.m.nv))
        jr = jp.copy()
        mujoco.mj_jacBody(self.m, d, jp, jr, body)
        return np.r_[jp, jr]

    def dotbias(self, key, jac, d):
        bias = np.zeros(jac.shape[0]) if key not in self.prev else (jac - self.prev[key]) @ d.qvel / 0.004
        self.prev[key] = jac.copy()
        return bias

    def command(self, d):
        m = self.m
        nv = m.nv
        t = float(d.time)
        elapsed = t - self.start
        jcom = np.zeros((3, nv))
        mujoco.mj_jacSubtreeCom(m, d, jcom, 1)
        comvel = jcom @ d.qvel
        floor = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, 'floor')
        forces = []
        counts = []
        for side in ('left', 'right'):
            ids = {mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f'{side}_foot{i}_collision') for i in (1, 2, 3)}
            normal = 0.0
            count = 0
            for idx, c0 in enumerate(d.contact):
                if floor in {int(c0.geom1), int(c0.geom2)} and {int(c0.geom1), int(c0.geom2)} & ids:
                    f = np.zeros(6)
                    mujoco.mj_contactForce(m, d, idx, f)
                    normal += max(0, float(f[0]))
                    count += 1
            forces.append(normal)
            counts.append(count)
        nextphase = None
        if self.phase == 'settle':
            self.comgoal = self.com_initial.copy()
            self.comgoal[2] -= CONFIG['drop'] * smooth(t / CONFIG['settle_s'])
            if t >= CONFIG['settle_s']:
                nextphase = 'shift_right'
        elif self.phase in ('shift_right', 'shift_left', 'recover'):
            side = 1 if self.phase == 'shift_right' else 0
            target = np.mean(self.footgoal, axis=0) if self.phase == 'recover' else self.footgoal[side].copy()
            if self.phase != 'recover':
                target[1] += (-1 if side == 0 else 1) * CONFIG['support_inward_m']
            target[0] += CONFIG['support_x_offset']
            target[2] = self.com_initial[2] - CONFIG['drop']
            self.comgoal = self.transfer_start + (target - self.transfer_start) * smooth(elapsed / (CONFIG['recover_s'] if self.phase == 'recover' else CONFIG['transfer_s']))
            ready = elapsed >= CONFIG['transfer_s'] and np.linalg.norm(d.subtree_com[1, :2] - target[:2]) < 0.025 and (np.linalg.norm(comvel[:2]) < 0.06)
            if self.phase != 'recover':
                ready = ready and forces[side] > 260 and (forces[1 - side] < 60)
            self.gate = self.gate + 1 if ready else 0
            if self.gate >= 20 and self.phase != 'recover':
                nextphase = 'swing_left' if side == 1 else 'swing_right'
        elif self.phase in ('swing_left', 'swing_right'):
            i = 0 if self.phase == 'swing_left' else 1
            progress = min(1.0, elapsed / CONFIG['swing_s'])
            self.footgoal[i] = self.swing_start + (self.swing_target - self.swing_start) * smooth(progress)
            self.footgoal[i][2] += 0.04 * math.sin(math.pi * progress) ** 2
            landed = progress >= 1 and forces[i] > 0.5 and (counts[i] > 0) and (abs(d.xpos[self.bodies[i], 2] - self.footgoal[i][2]) < 0.003)
            self.gate = self.gate + 1 if landed else 0
            if self.gate >= 25:
                self.footgoal[i] = d.xpos[self.bodies[i]].copy()
                self.completed_swings += 1
                nextphase = ('recover' if self.completed_swings >= CONFIG['planned_steps']
                             else 'shift_left' if i == 0 else 'shift_right')
        if nextphase:
            self.events.append({'time': t, 'from': self.phase, 'to': nextphase, 'normal_forces_n': forces.copy()})
            self.phase = nextphase
            if self.phase in ('swing_left', 'swing_right'):
                i = 0 if self.phase == 'swing_left' else 1
                self.swing_start = self.footgoal[i].copy()
                self.swing_target = self.foot_initial[i].copy()
                self.swing_target[0] = self.footgoal[1-i][0] + CONFIG['step_m']
                self.swing_target[2] -= CONFIG['landing_depth_m']
            self.start = t
            self.transfer_start = self.comgoal.copy()
            self.gate = 0
            elapsed = 0.0
        swing = 0 if self.phase == 'swing_left' else 1 if self.phase == 'swing_right' else None
        stance = [i for i in (0, 1) if i != swing]
        nf = 6 * len(stance)
        n = nv + nf
        mass = np.zeros((nv, nv))
        mujoco.mj_fullM(m, d, mass)
        bias = d.qfrc_bias - d.qfrc_passive
        jf = [self.jac(d, b) for b in self.bodies]
        jbias = [self.dotbias('foot' + str(i), jf[i], d) for i in (0, 1)]
        desiredfeet = []
        for i, b in enumerate(self.bodies):
            error = np.r_[self.footgoal[i] - d.xpos[b], orientation_error(self.footrot[i], d.xmat[b].reshape(3, 3))]
            velocity = np.zeros(6)
            acceleration = np.zeros(6)
            if i == swing and elapsed < CONFIG['swing_s']:
                progress = elapsed / CONFIG['swing_s']
                duration = CONFIG['swing_s']
                delta = self.swing_target - self.swing_start
                velocity[:3] = delta * 30 * progress ** 2 * (1 - progress) ** 2 / duration
                acceleration[:3] = delta * 60 * progress * (1 - progress) * (1 - 2 * progress) / duration ** 2
                velocity[2] += 0.04 * math.pi * math.sin(2 * math.pi * progress) / duration
                acceleration[2] += 0.08 * math.pi ** 2 * math.cos(2 * math.pi * progress) / duration ** 2
            desiredfeet.append(400 * error + 40 * (velocity - jf[i] @ d.qvel) + acceleration - jbias[i])
        j = np.concatenate([jf[i] for i in stance], axis=0)
        nc = 6 + nf
        c = np.zeros((nc, n))
        c[:6, :nv] = mass[:6]
        c[:6, nv:] = -j[:, :6].T
        c[6:, :nv] = j
        rhs = np.r_[-bias[:6], np.concatenate([desiredfeet[i] for i in stance])]
        jroot = self.jac(d, 1)[3:]
        rootjac = np.r_[jcom, jroot]
        rooterr = np.r_[self.comgoal - d.subtree_com[1], orientation_error(np.eye(3), d.xmat[1].reshape(3, 3))]
        desiredroot = CONFIG['root_kp'] * rooterr - 2 * math.sqrt(CONFIG['root_kp']) * (rootjac @ d.qvel) - self.dotbias('root', rootjac, d)
        nt = 6 + 29 + nf + (6 if swing is not None else 0)
        task = np.zeros((nt, n))
        values = np.zeros(nt)
        task[:6, :nv] = 10 * rootjac
        values[:6] = 10 * desiredroot
        weights = np.full(29, CONFIG['joint_weight'])
        weights[12:] = CONFIG['upper_weight']
        task[6:35, 6:nv] = np.diag(weights)
        values[6:35] = weights * (40 * (self.qhome - d.qpos[7:]) - 10 * d.qvel[6:])
        moment_weights = np.tile([0.01, 0.01, 0.01, CONFIG['moment_weight'], CONFIG['moment_weight'], CONFIG['moment_weight']], len(stance))
        task[35:35 + nf, nv:] = np.diag(moment_weights)
        totalmass = float(sum(m.body_mass))
        desiredcop = d.subtree_com[1, :2] - desiredroot[:2] * d.subtree_com[1, 2] / 9.81
        left_fraction = float(np.clip((desiredcop[1] - self.footgoal[1][1]) / (self.footgoal[0][1] - self.footgoal[1][1]), 0.0, 1.0))
        fractions = [left_fraction if i == 0 else 1 - left_fraction for i in stance] if len(stance) == 2 else [1.0]
        for k, i in enumerate(stance):
            fz = totalmass * (9.81 + desiredroot[2]) * fractions[k]
            desiredwrench = np.r_[totalmass * desiredroot[:2] * fractions[k], fz, 0.0, -fz * (desiredcop[0] - self.footgoal[i][0]), 0.0]
            values[35 + 6 * k:35 + 6 * k + 6] = moment_weights[6 * k:6 * k + 6] * desiredwrench
        if swing is not None:
            task[-6:, :nv] = 10 * jf[swing]
            values[-6:] = 10 * desiredfeet[swing]
        h = task.T @ task + np.eye(n) * 1e-06
        g = task.T @ values
        kkt = np.block([[h, c.T], [c, np.zeros((nc, nc))]])
        sol = np.linalg.solve(kkt, np.r_[g, rhs])
        torque_a = np.c_[mass[6:], -j[:, 6:].T]
        low = np.maximum(m.actuator_forcerange[:, 0], self.gains * (self.low - d.qpos[7:]) - 2 * d.qvel[6:])
        high = np.minimum(m.actuator_forcerange[:, 1], self.gains * (self.high - d.qpos[7:]) - 2 * d.qvel[6:])
        inequalities = [*torque_a, *-torque_a]
        bounds = [*high - bias[6:], *-low + bias[6:]]
        for k in range(len(stance)):
            baseidx = nv + 6 * k
            row = np.zeros(n)
            row[baseidx + 2] = -1
            inequalities.append(row)
            bounds.append(0.0)
            for axis, scale in ((0, 0.5), (1, 0.5), (3, 0.025), (4, 0.05), (5, 0.02)):
                for sign in (-1, 1):
                    row = np.zeros(n)
                    row[baseidx + axis] = sign
                    row[baseidx + 2] = -((0.15 if sign == -1 else 0.05) if axis == 4 else scale)
                    inequalities.append(row)
                    bounds.append(0.0)
        ia = np.array(inequalities)
        ib = np.array(bounds)
        active = []
        residual = 0.0
        for iteration in range(64):
            violations = ia @ sol[:n] - ib
            residual = float(max(violations))
            if residual < 1e-05:
                break
            multipliers = sol[n + nc:]
            if active and len(multipliers) == len(active) and (min(multipliers) < -1e-06):
                active.pop(int(np.argmin(multipliers)))
            else:
                scaled_violations = violations / np.maximum(np.linalg.norm(ia, axis=1), 1e-08)
                choices = [int(i) for i in np.argsort(scaled_violations)[::-1] if violations[i] > 1e-05 and int(i) not in active]
                if not choices:
                    break
                active.append(choices[0])
            ca = np.r_[c, ia[active]]
            rb = np.r_[rhs, ib[active]]
            scale = np.maximum(np.linalg.norm(ca, axis=1), 1e-08)
            ca = ca / scale[:, None]
            rb = rb / scale
            try:
                sol = np.linalg.solve(np.block([[h, ca.T], [ca, np.zeros((len(rb), len(rb)))]]), np.r_[g, rb])
            except np.linalg.LinAlgError:
                break
        residual = float(np.max(ia @ sol[:n] - ib))
        equality_residual = float(np.max(np.abs(c @ sol[:n] - rhs)))
        if not np.all(np.isfinite(sol)) or residual > 0.0001 or equality_residual > 0.0001:
            raise ControllerFeasibilityError(f'controller feasibility guard at t={t}, phase={self.phase}, inequality={residual}, equality={equality_residual}; no gait acceptance')
        acc = sol[:nv]
        wrench = sol[nv:n]
        tau = torque_a @ sol[:n] + bias[6:]
        raw = d.qpos[7:] + (tau + 2 * d.qvel[6:]) / self.gains
        limited = np.clip(raw, self.low, self.high)
        self.clipped_target_observations += int(np.count_nonzero(raw != limited))
        self.maximum_target_delta_rad = max(self.maximum_target_delta_rad, float(np.max(np.abs(limited - d.ctrl))))
        self.control_trace.append({'t': t, 'phase': self.phase, 'normal_forces_n': forces, 'contacts': counts, 'foot_clearance_m': self.foot_clearance(d), 'feet': [d.xpos[b].tolist() for b in self.bodies], 'foot_targets': [v.tolist() for v in self.footgoal], 'com_target': self.comgoal.tolist(), 'joint_position': d.qpos[7:].tolist(), 'root_linear_velocity_m_s': d.qvel[:3].tolist(), 'root_angular_velocity_rad_s': d.qvel[3:6].tolist(), 'maximum_joint_rate_rad_s': float(np.max(np.abs(d.qvel[6:]))), 'qp_iterations': iteration + 1, 'constraint_residual': residual, 'active_constraints': len(active), 'predicted_wrenches': wrench.tolist(), 'max_torque': float(np.max(abs(tau))), 'clipped': int(np.count_nonzero(raw != limited)), 'root': d.qpos[:3].tolist(), 'com': d.subtree_com[1].tolist()})
        self.controller_end = {'phase': self.phase, 'events': self.events.copy(), 'foot_initial': self.foot_initial.tolist(), 'foot_final': [d.xpos[b].tolist() for b in self.bodies]}
        return limited

    def foot_clearance(self, data):
        """Actual lowest source foot-capsule surface above the z=0 floor."""
        return [min(float(data.geom_xpos[g, 2] - self.m.geom_size[g, 0]
                          - self.m.geom_size[g, 1] * abs(data.geom_xmat[g, 8]))
                    for g in group) for group in self.foot_geoms]

    def probe_report(self, data, *, include_trace=False):
        from .freebase_sustained_metrics import summarize_sustained_probe
        floor = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_GEOM, 'floor')
        forces, contacts = [], []
        for group in self.foot_geoms:
            normal, count = 0., 0
            for index, contact in enumerate(data.contact):
                pair = {int(contact.geom1), int(contact.geom2)}
                if floor in pair and pair.intersection(group):
                    force = np.zeros(6)
                    mujoco.mj_contactForce(self.m, data, index, force)
                    normal += max(0., float(force[0]))
                    count += 1
            forces.append(normal)
            contacts.append(count)
        final_observation = {
            't': float(data.time), 'phase': self.phase, 'sample_kind': 'final_post_step',
            'normal_forces_n': forces, 'contacts': contacts,
            'feet': [data.xpos[b].tolist() for b in self.bodies],
            'root': data.qpos[:3].tolist(), 'com': data.subtree_com[1].tolist(),
            'foot_clearance_m': self.foot_clearance(data),
            'root_linear_velocity_m_s': data.qvel[:3].tolist(),
            'root_angular_velocity_rad_s': data.qvel[3:6].tolist(),
            'maximum_joint_rate_rad_s': float(np.max(np.abs(data.qvel[6:])))}
        trace = [*self.control_trace, final_observation]
        result = summarize_sustained_probe(
            trace, self.events, self.foot_initial.tolist(),
            final_observation['feet'], self.initial_root.tolist(), data.qpos[:3].tolist(),
            final_observation['foot_clearance_m'], float(data.time))
        result['controller_parameters'] = dict(CONFIG)
        result['numpy_version'] = np.__version__
        result['final_gait_observation'] = final_observation
        if include_trace:
            result['gait_trace'] = trace
        return result
