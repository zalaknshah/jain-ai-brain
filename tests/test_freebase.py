import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from jace.freebase import SCENARIOS, run_freebase_diagnostic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'src' / 'jace' / 'data'


class FreebaseContractTests(unittest.TestCase):
    def test_invalid_or_unconfirmed_call_never_starts_worker(self):
        with patch('jace.freebase.subprocess.run') as worker:
            for options in ({}, {'confirm_simulation': False}, {'confirm_simulation': 'yes'},
                            {'confirm_simulation': True, 'scenario': 'custom.xml'},
                            {'confirm_simulation': True, 'steps': True}, {'confirm_simulation': True, 'steps': 0},
                            {'confirm_simulation': True, 'steps': 2001}, {'confirm_simulation': True, 'include_trace': 1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    run_freebase_diagnostic(**options)
            worker.assert_not_called()

    def test_internal_runner_also_requires_confirmation(self):
        from jace.freebase_worker import _run
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            _run('neutral_posture', 10, False)

    def test_clean_subprocess_contract_and_timeout(self):
        response = subprocess.CompletedProcess([], 0, '{"schema":"jace.freebase.diagnostic.v1"}', '')
        with patch.dict(os.environ, {'JACE_AUTH_TOKENS': 'synthetic-test-only', 'MODEL_KEY': 'synthetic-placeholder'}):
            with patch('jace.freebase.subprocess.run', return_value=response) as worker:
                run_freebase_diagnostic(confirm_simulation=True)
        args, kwargs = worker.call_args
        self.assertIn('--confirmed-simulation', args[0])
        self.assertNotIn('JACE_AUTH_TOKENS', kwargs['env'])
        self.assertNotIn('MODEL_KEY', kwargs['env'])
        self.assertEqual(kwargs['env']['OMP_NUM_THREADS'], '1')
        self.assertEqual(kwargs['timeout'], 30)
        self.assertNotIn('shell', kwargs)

    def test_worker_failures_never_retry_or_claim_success(self):
        failures = [subprocess.CompletedProcess([], 137, '', 'killed'),
                    subprocess.CompletedProcess([], 0, 'not json', ''),
                    subprocess.CompletedProcess([], 0, '{"schema":"wrong"}', '')]
        for failure in failures:
            with self.subTest(failure=failure), patch('jace.freebase.subprocess.run', return_value=failure) as worker:
                with self.assertRaises(RuntimeError):
                    run_freebase_diagnostic(confirm_simulation=True)
                self.assertEqual(worker.call_count, 1)
        with patch('jace.freebase.subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 30)) as worker:
            with self.assertRaisesRegex(RuntimeError, 'wall-time cap'):
                run_freebase_diagnostic(confirm_simulation=True)
            self.assertEqual(worker.call_count, 1)

    def test_no_unrestricted_nonposix_fallback(self):
        with patch('jace.freebase.os.name', 'nt'), patch('jace.freebase.subprocess.run') as worker:
            with self.assertRaisesRegex(RuntimeError, 'resource limits'):
                run_freebase_diagnostic(confirm_simulation=True)
            worker.assert_not_called()

    def test_derivative_reproduces_and_preserves_physical_source_parameters(self):
        spec = importlib.util.spec_from_file_location('derive_g1', ROOT / 'scripts' / 'derive_headless_g1.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            result = module.derive(Path(directory))
            for name in (*result['runtime_sha256'], 'unitree_g1_source.json', 'unitree_g1_LICENSE.txt'):
                self.assertEqual((Path(directory) / name).read_bytes(), (DATA / name).read_bytes())
        source = ROOT / 'third_party' / 'unitree_g1'
        original = ET.parse(source / 'g1_mjx.xml').getroot()
        modified = ET.parse(DATA / 'unitree_g1_headless.xml').getroot()
        for tag in ('body', 'inertial', 'joint', 'freejoint', 'position', 'site', 'option', 'flag'):
            self.assertEqual([x.attrib for x in original.findall('.//' + tag)],
                             [x.attrib for x in modified.findall('.//' + tag)], tag)
        scene = ET.parse(source / 'scene_mjx.xml').getroot()
        headless = ET.parse(DATA / 'unitree_g1_scene.xml').getroot()
        for tag in ('pair', 'key', 'geom'):
            self.assertEqual([x.attrib for x in scene.findall('.//' + tag)],
                             [x.attrib for x in headless.findall('.//' + tag)], tag)
        self.assertEqual(result['removed_zero_density_visual_geoms'], 35)
        self.assertEqual(result['preserved_contact_pairs'], 49)
        self.assertTrue(all(body.find('inertial') is not None for body in modified.findall('.//body')))
        self.assertFalse(modified.findall('.//mesh'))

    def test_license_and_modified_notice_are_packaged_sources(self):
        self.assertIn('Redistribution and use', (DATA / 'unitree_g1_LICENSE.txt').read_text())
        self.assertIn('Modified', (DATA / 'unitree_g1_NOTICE.txt').read_text())
        self.assertIn('not a validated', (DATA / 'unitree_g1_NOTICE.txt').read_text())


@unittest.skipUnless(os.name == 'posix' and importlib.util.find_spec('mujoco'), 'POSIX and optional MuJoCo required; real diagnostic not run')
class RealFreebaseTests(unittest.TestCase):
    def test_neutral_servo_instability_is_an_explicit_failure(self):
        report = run_freebase_diagnostic(confirm_simulation=True, include_trace=True)
        self.assertEqual(report['terminal_reason'], 'posture_guard_triggered')
        self.assertFalse(report['no_guard_triggered_within_horizon'])
        self.assertFalse(report['standing_verified'])
        self.assertFalse(report['locomotion_controller'])
        self.assertFalse(report['pretrained_policy_loaded'])
        self.assertFalse(report['hardware_enabled'])
        self.assertTrue(report['free_base'])
        self.assertEqual(report['actuated_joints'], 29)
        self.assertGreater(report['maximum_tilt_rad'], .5)
        self.assertLess(report['steps'], 1250)
        self.assertAlmostEqual(report['elapsed_simulation_s'], report['steps'] * .004)
        self.assertEqual(len(report['trace']), report['steps'])
        self.assertGreater(report['maximum_foot_contact_points'], 0)
        self.assertLess(report['peak_rss_kib'], 1024**2)
        json.dumps(report, allow_nan=False)

    def test_push_cases_report_outcome_without_balance_claim(self):
        for scenario in ('forward_push', 'lateral_push'):
            with self.subTest(scenario=scenario):
                report = run_freebase_diagnostic(scenario, confirm_simulation=True)
                self.assertNotEqual(report['terminal_reason'], 'step_budget_reached')
                self.assertFalse(report['standing_verified'])
                self.assertLess(report['steps'], 1250)

    def test_initial_bad_posture_stops_before_first_step(self):
        report = run_freebase_diagnostic('initial_tilt', confirm_simulation=True)
        self.assertEqual(report['steps'], 0)
        self.assertEqual(report['elapsed_simulation_s'], 0)
        self.assertEqual(report['terminal_reason'], 'posture_guard_triggered')

    def test_sensor_loss_does_not_take_an_extra_step(self):
        report = run_freebase_diagnostic('sensor_dropout', confirm_simulation=True, include_trace=True)
        self.assertEqual(report['steps'], 100)
        self.assertAlmostEqual(report['elapsed_simulation_s'], .4)
        self.assertEqual(report['terminal_reason'], 'sensor_guard_triggered')

    def test_short_horizon_is_not_a_standing_claim(self):
        report = run_freebase_diagnostic(steps=10, confirm_simulation=True)
        self.assertTrue(report['no_guard_triggered_within_horizon'])
        self.assertFalse(report['standing_verified'])
        self.assertEqual(report['steps'], 10)
        self.assertNotIn('trace', report)

    def test_physics_repeatability_excludes_process_memory_usage(self):
        first = run_freebase_diagnostic(confirm_simulation=True)
        second = run_freebase_diagnostic(confirm_simulation=True)
        first.pop('peak_rss_kib'); second.pop('peak_rss_kib')
        self.assertEqual(first, second)
