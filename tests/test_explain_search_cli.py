import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jace import cli


class ExplainSearchCliTests(unittest.TestCase):
    def invoke(self, *args, output=None):
        stdout, stderr = output if output is not None else io.StringIO(), io.StringIO()
        with patch('sys.argv', ['jace', 'explain-search', *args]), \
             patch('jace.cli.CognitiveEngine', side_effect=AssertionError('engine forbidden')), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                cli.main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def test_disclosure_required_before_any_store_read(self):
        with patch('jace.canonical.CanonicalStore', side_effect=AssertionError('read forbidden')):
            code, out, err = self.invoke('compassion')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('--allow-local-disclosure', err)

    def test_sample_only_ignores_environment_and_creates_no_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'JACE_CANONICAL_PATH': '/missing/private', 'JACE_DB_PATH': directory+'/never.sqlite'}):
                code, out, err = self.invoke('compassion', '--allow-local-disclosure')
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(report['mode'], 'lexical-only')
        self.assertFalse(report['semantic_support_verified'])
        self.assertFalse(report['runtime_admitted'])

    def fixture(self, directory):
        path = Path(directory) / 'private.json'
        path.write_text(json.dumps([dict(entry_id='synthetic',title='करुणा',principle='Secret passage not disclosed',
            guidance='Other secret guidance',source='Secret provenance',tags=[],work='Secret work',language='hi',
            location='Secret location',license='Synthetic fixture',verified=True)]))
        return path

    def test_explicit_corpus_reports_matches_not_passages_or_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            before = path.read_bytes()
            code, out, err = self.invoke('करुणा','--corpus',str(path),'--allow-local-disclosure')
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn(directory, out+err)
        self.assertEqual(code, 0, err)
        hit = json.loads(out)['hits'][0]
        self.assertEqual(hit['field_matches'], {'title':['करुणा']})
        self.assertEqual(hit['entry_id'], 'synthetic')
        self.assertNotIn('Secret', out+err)

    def test_invalid_query_and_limit_precede_source_read(self):
        for args in [('x'*10001,), ('query','--limit','0'), ('query','--limit','101'),
                     ('query','--limit','/sensitive/private-path')]:
            with patch('jace.canonical.CanonicalStore', side_effect=AssertionError('read forbidden')):
                code, out, err = self.invoke(*args,'--allow-local-disclosure')
            self.assertEqual(code, 2)
            self.assertEqual(out, '')
            self.assertNotIn('/sensitive/private-path', err)

    def test_write_failure_is_sanitized_and_partial_output_is_explicit(self):
        class FailingOutput(io.StringIO):
            def write(self, text):
                super().write(text[:12])
                raise OSError('write failed at /sensitive/private-output')
        code, out, err = self.invoke('query','--allow-local-disclosure', output=FailingOutput())
        self.assertEqual(code, 2)
        self.assertTrue(out)
        self.assertIn('output may be incomplete', err)
        self.assertNotIn('/sensitive', err)
        self.assertNotIn('Traceback', err)

    def test_flush_failure_is_sanitized(self):
        class FailingOutput(io.StringIO):
            def flush(self):
                raise OSError('flush failed at /sensitive/private-output')
        code, out, err = self.invoke('query','--allow-local-disclosure', output=FailingOutput())
        self.assertEqual(code, 2)
        self.assertTrue(out)
        self.assertIn('output may be incomplete', err)
        self.assertNotIn('/sensitive', err)

    @unittest.skipUnless(sys.platform.startswith('linux') and Path('/dev/full').exists(),
                         'requires Linux /dev/full output-device fixture')
    def test_real_output_device_failure_has_nonzero_status(self):
        root = Path(__file__).resolve().parents[1]
        environment = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
        with open('/dev/full', 'wb') as output:
            result = subprocess.run(
                [sys.executable, '-m', 'jace.cli', 'explain-search', 'compassion',
                 '--allow-local-disclosure'], cwd=root, env=environment,
                stdout=output, stderr=subprocess.PIPE, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('output may be incomplete', result.stderr)
        # Python may replace SystemExit(2) with 120 if shutdown flushing fails.
        # This test intentionally does not promise an exact process status.

    def test_missing_or_empty_corpus_fails_without_path_disclosure(self):
        for path in ('/private-secret-path/not-here.json', ''):
            code, out, err = self.invoke('query','--corpus',path,'--allow-local-disclosure')
            self.assertEqual(code, 2)
            self.assertEqual(out, '')
            self.assertNotIn('private-secret', err)

    def test_symlink_corpus_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            link = Path(directory)/'link.json'; link.symlink_to(path)
            code, out, err = self.invoke('करुणा','--corpus',str(link),'--allow-local-disclosure')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')

    def test_unavailable_secure_io_remains_closed(self):
        with patch('jace.source_bundle._safe_io_missing', return_value=['synthetic missing prerequisite']):
            code, out, err = self.invoke('query','--corpus','/private/source','--allow-local-disclosure')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertNotIn('/private/source', err)

    def test_output_budget_fails_without_partial_json(self):
        with patch('jace.cli.json.dumps', return_value='x'*(1024*1024+1)):
            code, out, err = self.invoke('query','--allow-local-disclosure')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')

if __name__ == '__main__': unittest.main()
