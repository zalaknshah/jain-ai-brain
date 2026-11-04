"""Platform feature inspection is not native filesystem qualification."""
import contextlib
import ctypes
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jace import source_bundle as sb
from jace import source_review as sr
from jace import bundle_builder as builder
from jace import cli


META = dict(work='Original synthetic fixture', source='Fixture author', language='en',
            license_name='MIT fixture', location='Synthetic section')


def simulated_os(**changes):
    values = vars(os).copy()
    values.update(changes)
    return SimpleNamespace(**values)


class SourcePlatformTests(unittest.TestCase):
    def test_report_has_no_paths_or_verified_filesystem_claim(self):
        with patch.object(sb, '_publication_primitive') as primitive, \
             patch.object(sb, '_DirectoryChain', side_effect=AssertionError('No source IO')), \
             patch.object(sb, '_write_bundle', side_effect=AssertionError('No output')), \
             patch.object(sb, '_rename_noreplace', side_effect=AssertionError('No rename')):
            report = sb.source_platform_capabilities()
        primitive.assert_called_once_with()
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['platform'], sys.platform)
        self.assertIn('prerequisites_available', report['external_source_reads'])
        self.assertIn('not implemented', report['native_windows_source_backend'])
        self.assertIn('do not prove', ' '.join(report['limits']))
        self.assertIn('was not loaded', report['built_in_samples'])
        self.assertNotIn(str(Path.cwd()), json.dumps(report))

    def test_simulated_windows_fails_without_loading_libc(self):
        windows = simulated_os(name='nt', supports_dir_fd=set(), supports_follow_symlinks=set(), supports_fd=set())
        for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_CLOEXEC', 'O_NONBLOCK'):
            if hasattr(windows, flag):
                delattr(windows, flag)
        with patch.object(sb, 'os', windows), patch.object(sb, 'sys', SimpleNamespace(platform='win32')), \
             patch.object(sb.ctypes, 'CDLL', side_effect=AssertionError('No Windows libc probe')):
            report = sb.source_platform_capabilities()
            self.assertFalse(report['external_source_reads']['prerequisites_available'])
            self.assertFalse(report['private_bundle_publication']['prerequisites_available'])
            self.assertIn('posix_os', report['external_source_reads']['missing_prerequisites'])
            self.assertIn('linux_platform', report['private_bundle_publication']['missing_prerequisites'])
            with self.assertRaisesRegex(ValueError, 'source-capabilities'):
                sb._require_publication_io()

    def test_nonlinux_posix_distinguishes_reads_and_publication(self):
        with patch.object(sb, 'sys', SimpleNamespace(platform='darwin')), \
             patch.object(sb, '_safe_io_missing', return_value=[]), \
             patch.object(sb.ctypes, 'CDLL', side_effect=AssertionError('No non-Linux libc probe')):
            report = sb.source_platform_capabilities()
            self.assertTrue(report['external_source_reads']['prerequisites_available'])
            self.assertFalse(report['private_bundle_publication']['prerequisites_available'])
            self.assertIn('linux_platform', report['private_bundle_publication']['missing_prerequisites'])
            with self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                sb._require_publication_io()

    def test_read_primitives_include_directory_enumeration(self):
        cases = [({'supports_dir_fd': set()}, 'open_dir_fd'),
                 ({'supports_follow_symlinks': set()}, 'stat_no_follow'),
                 ({'supports_fd': set()}, 'scandir_fd')]
        for changes, missing in cases:
            with self.subTest(missing=missing), patch.object(sb, 'os', simulated_os(**changes)):
                self.assertIn(missing, sb._safe_io_missing())
                with self.assertRaisesRegex(ValueError, 'source-capabilities'):
                    sb._require_safe_io()

    def test_publication_primitives_include_private_writes_and_cleanup(self):
        for name in ('mkdir', 'unlink', 'rmdir'):
            reduced = os.supports_dir_fd - {getattr(os, name)}
            with self.subTest(name=name), patch.object(sb, 'os', simulated_os(supports_dir_fd=reduced)), \
                 patch.object(sb, '_safe_io_missing', return_value=[]):
                self.assertIn(name + '_dir_fd', sb._publication_io_missing())
                with self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                    sb._require_publication_io()
        for name in ('fchmod', 'fsync'):
            with self.subTest(name=name), patch.object(sb, 'os', simulated_os(**{name:None})), \
                 patch.object(sb, '_safe_io_missing', return_value=[]):
                self.assertIn(name, sb._publication_io_missing())
                with self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                    sb._require_publication_io()

    def test_unavailable_libc_or_symbol_reports_without_rename(self):
        with patch.object(sb, 'sys', SimpleNamespace(platform='linux')):
            for result, code in ((SimpleNamespace(), 'libc_renameat2'), (OSError('unavailable'), 'libc_unavailable')):
                options = {'side_effect': result} if isinstance(result, Exception) else {'return_value': result}
                with self.subTest(code=code), patch.object(sb.ctypes, 'CDLL', **options):
                    report = sb.source_platform_capabilities()
                    self.assertFalse(report['private_bundle_publication']['prerequisites_available'])
                    self.assertIn(code, report['private_bundle_publication']['missing_prerequisites'])
                    with self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                        sb._require_publication_io()

    def test_api_presence_does_not_replace_final_syscall_or_error(self):
        class Rename:
            calls = 0
            def __call__(self, *args):
                self.calls += 1
                ctypes.set_errno(sb.errno.EOPNOTSUPP)
                return -1
        rename = Rename()
        with patch.object(sb, '_publication_primitive', return_value=rename), \
             patch.object(sb, '_safe_io_missing', return_value=[]), \
             patch.object(sb, '_publication_io_missing', return_value=[]):
            report = sb.source_platform_capabilities()
            sb._require_publication_io()
            self.assertTrue(report['private_bundle_publication']['prerequisites_available'])
            self.assertEqual(rename.calls, 0)
            with self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                sb._rename_noreplace(1, 'fixture-stage', 'fixture-target')
            self.assertEqual(rename.calls, 1)

    def test_publication_checks_before_input_iteration_or_source_reads(self):
        class NoIteration:
            def __iter__(self): raise AssertionError('No input iteration')
        with patch.object(sb, 'sys', SimpleNamespace(platform='darwin')), \
             patch.object(sb, '_safe_io_missing', return_value=[]), \
             patch.object(sb, '_publication_io_missing', return_value=[]), \
             patch.object(sb, 'read_source_file', side_effect=AssertionError('No source read')), \
             patch.object(builder, 'read_source_file', side_effect=AssertionError('No source read')), \
             patch.object(sr, '_read_review_snapshot', side_effect=AssertionError('No draft read')), \
             patch.object(sr, '_read_decisions', side_effect=AssertionError('No decision read')), \
             patch.object(sb, '_DirectoryChain', side_effect=AssertionError('No staging')):
            for operation in (
                lambda: builder.build_exact_bundle(NoIteration(), 'unused', **META, verified=True, confirm_build=True),
                lambda: sr.prepare_source_review(NoIteration(), 'unused', **META, confirm_copy=True),
                lambda: sr.export_reviewed_sources('unused', 'unused', 'unused', confirm_export=True,
                    declare_qualified_review=True, declare_rights_for_local_retrieval=True),
                lambda: sb.write_source_bundle('unused', {}, []),
            ):
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'publication is unavailable'):
                    operation()

    def test_confirmation_still_precedes_platform_preflight(self):
        with patch.object(sb, '_require_publication_io', side_effect=AssertionError('No check before consent')), \
             patch.object(builder, '_require_publication_io', side_effect=AssertionError('No check before consent')):
            for operation in (
                lambda: builder.build_exact_bundle([], 'unused', **META),
                lambda: sr.prepare_source_review([], 'unused', **META),
                lambda: sr.export_reviewed_sources('unused', 'unused', 'unused'),
            ):
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'explicit|Explicit'):
                    operation()

    def test_main_cli_never_instantiates_engine(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['jace', 'source-capabilities']), \
             patch.object(cli, 'CognitiveEngine', side_effect=AssertionError('No engine')), \
             contextlib.redirect_stdout(output):
            cli.main()
        self.assertEqual(json.loads(output.getvalue())['schema_version'], 1)

    def test_both_cli_paths_ignore_external_configuration_and_create_nothing(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, 'PYTHONPATH':str(root/'src'), 'JACE_DB_PATH':str(Path(temp)/'must-not-exist.db'),
                   'JACE_CANONICAL_PATH':'/unread/not-a-source.json', 'JACE_MODEL_URL':'http://invalid.invalid'}
            commands = [[sys.executable, '-m', 'jace.cli', 'source-capabilities'],
                        [sys.executable, str(root/'scripts/review_sources.py'), 'capabilities']]
            for command in commands:
                run = subprocess.run(command, cwd=temp, env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout)['schema_version'], 1)
                self.assertEqual(list(Path(temp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
