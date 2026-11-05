import ast
import builtins
from importlib import metadata
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from jace.freebase import run_freebase_diagnostic
from jace.freebase_balance import run_freebase_balance
from jace.freebase_gait import (GAIT_DEPENDENCIES, run_gait_probe,
                                validate_gait_backend_versions, validate_gait_runtime)
from jace.freebase_worker import _run

ROOT = Path(__file__).resolve().parents[1]


class GaitRuntimeCompatibilityTests(unittest.TestCase):
    def test_optional_extras_do_not_raise_legacy_python_requirement(self):
        text = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('requires-python = ">=3.10"', text)
        section = text.split('[project.optional-dependencies]\n', 1)[1].split('\n[', 1)[0]
        extras = {}
        for line in section.splitlines():
            if line.strip() and not line.startswith('#'):
                name, _, value = line.partition('=')
                extras[name.strip()] = ast.literal_eval(value.strip())
        self.assertEqual(extras['simulation'], ['mujoco==3.17.0'])
        self.assertEqual(extras['gait'], ['mujoco==3.17.0', 'numpy==2.5.4'])

    def test_unsupported_python_stops_before_metadata_import_or_worker(self):
        original_import = builtins.__import__
        backend_imports = []
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in {'mujoco', 'numpy'}:
                backend_imports.append(name)
                raise AssertionError('backend imported before runtime qualification')
            return original_import(name, *args, **kwargs)
        for version in ((3, 10, 16), (3, 11, 12)):
            with self.subTest(version=version), patch('jace.freebase_gait.sys.version_info', version), \
                    patch('jace.freebase_gait.metadata.version') as lookup, \
                    patch('jace.freebase.subprocess.run') as worker, \
                    patch('builtins.__import__', side_effect=guarded_import):
                with self.assertRaisesRegex(RuntimeError, r'Python 3\.12\+'):
                    run_gait_probe(confirm_simulation=True)
                lookup.assert_not_called()
                worker.assert_not_called()
        self.assertEqual(backend_imports, [])

    def test_missing_or_different_dependencies_never_start_worker(self):
        for name, actual in (('numpy', None), ('numpy', '2.2.0'), ('numpy', '2.5.5'),
                             ('mujoco', None), ('mujoco', '3.18.0')):
            def lookup(package):
                if package == name:
                    if actual is None:
                        raise metadata.PackageNotFoundError(package)
                    return actual
                return GAIT_DEPENDENCIES[package]
            with self.subTest(package=name, version=actual), \
                    patch('jace.freebase_gait.sys.version_info', (3, 12, 14)), \
                    patch('jace.freebase_gait.metadata.version', side_effect=lookup), \
                    patch('jace.freebase.subprocess.run') as worker:
                with self.assertRaisesRegex(RuntimeError, name + '=='):
                    run_gait_probe(confirm_simulation=True)
                worker.assert_not_called()

    def test_exact_qualified_versions_allow_preflight_without_backend_import(self):
        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in {'mujoco', 'numpy'}:
                raise AssertionError('metadata-only preflight imported a backend')
            return original_import(name, *args, **kwargs)
        with patch('jace.freebase_gait.sys.version_info', (3, 12, 14)), \
                patch('jace.freebase_gait.metadata.version', side_effect=GAIT_DEPENDENCIES.__getitem__), \
                patch('builtins.__import__', side_effect=guarded_import):
            validate_gait_runtime()

    def test_preflight_does_not_replace_explicit_simulation_confirmation(self):
        with patch('jace.freebase_gait.validate_gait_runtime') as preflight, \
                patch('jace.freebase.subprocess.run') as worker:
            with self.assertRaisesRegex(ValueError, 'simulation confirmation'):
                run_gait_probe()
            preflight.assert_not_called()
            worker.assert_not_called()

    def test_private_runner_rechecks_python_before_backend_import(self):
        original_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name.split('.')[0] in {'mujoco', 'numpy'}:
                raise AssertionError('private runner imported an unsupported backend')
            return original_import(name, *args, **kwargs)
        with patch('jace.freebase_gait.sys.version_info', (3, 11, 12)), \
                patch('builtins.__import__', side_effect=guarded_import):
            with self.assertRaisesRegex(RuntimeError, r'Python 3\.12\+'):
                _run('neutral_posture', 10, False, confirm_simulation=True, controller='contact_gait')

    def test_loaded_version_mismatch_stops_before_model_creation(self):
        for mujoco_version, numpy_version in (('3.18.0', '2.5.4'), ('3.17.0', '2.2.0')):
            constructor = Mock()
            fake_mujoco = SimpleNamespace(__version__=mujoco_version,
                                          MjModel=SimpleNamespace(from_xml_path=constructor))
            fake_numpy = SimpleNamespace(__version__=numpy_version)
            with self.subTest(mujoco=mujoco_version, numpy=numpy_version), \
                    patch('jace.freebase_gait.validate_gait_runtime'), \
                    patch.dict(sys.modules, {'mujoco': fake_mujoco, 'numpy': fake_numpy,
                                             'resource': SimpleNamespace()}):
                with self.assertRaisesRegex(RuntimeError, 'backend mismatch'):
                    _run('neutral_posture', 10, False, confirm_simulation=True, controller='contact_gait')
                constructor.assert_not_called()
        validate_gait_backend_versions('3.17.0', '2.5.4')

    def test_private_worker_reports_clear_runtime_block_before_physics(self):
        from jace.freebase_gait_worker import main
        argv = ['jace.freebase_gait_worker', 'neutral_posture', '10', 'summary', '--confirmed-simulation']
        with patch('sys.argv', argv), patch('jace.freebase_gait_worker._apply_resource_limits'), \
                patch('jace.freebase_gait.sys.version_info', (3, 10, 16)), \
                patch('builtins.print') as output:
            self.assertEqual(main(), 2)
        self.assertIn('Python 3.12+', output.call_args.args[0])

    def test_legacy_diagnostic_and_posture_paths_do_not_require_gait_stack(self):
        for runner, schema in ((run_freebase_diagnostic, 'jace.freebase.diagnostic.v1'),
                               (run_freebase_balance, 'jace.freebase.balance.v1')):
            response = subprocess.CompletedProcess([], 0, '{"schema":"' + schema + '"}', '')
            with self.subTest(schema=schema), \
                    patch('jace.freebase_gait.sys.version_info', (3, 10, 16)), \
                    patch('jace.freebase_gait.validate_gait_runtime', side_effect=AssertionError('gait-only gate reached')) as gate, \
                    patch('jace.freebase.subprocess.run', return_value=response) as worker:
                self.assertEqual(runner(confirm_simulation=True)['schema'], schema)
                gate.assert_not_called()
                self.assertEqual(worker.call_count, 1)
