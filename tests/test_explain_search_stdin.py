import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from jace import cli


class QueryInput:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)


class ExplainSearchStdinTests(unittest.TestCase):
    def invoke(self, data, *args):
        source = QueryInput(data)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('sys.stdin', source), patch('sys.argv', ['jace','explain-search',*args]), \
             patch('jace.cli.CognitiveEngine', side_effect=AssertionError('no engine')), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                cli.main(); code = 0
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue(), source.buffer.tell()

    def test_input_modes_are_exclusive_and_required(self):
        for args in [(), ('word','--stdin')]:
            code, out, err, read = self.invoke(b'{"query":"hidden"}', *args, '--allow-local-disclosure')
            self.assertEqual(code, 2)
            self.assertEqual(read, 0)
            self.assertEqual(out, '')

    def test_disclosure_gate_precedes_stdin_read(self):
        code, out, err, read = self.invoke(b'{"query":"hidden"}', '--stdin')
        self.assertEqual(code, 2)
        self.assertEqual(read, 0)
        self.assertEqual(out, '')

    def test_valid_stdin_matches_positional_report(self):
        for query in ('nonviolence','करुणा','કરુણા',''):
            data = json.dumps({'query':query}, ensure_ascii=False).encode()
            result = self.invoke(data, '--stdin', '--allow-local-disclosure')
            positional = self.invoke(b'', query, '--allow-local-disclosure')
            self.assertEqual(result[0], 0, result[2])
            self.assertEqual(json.loads(result[1]), json.loads(positional[1]))

    def test_invalid_json_schema_and_types_are_sanitized(self):
        for data in (b'', b'{"query":"secret","query":"other"}', b'{"private":"secret"}',
                     b'{"query":123}', b'{"query":"x","extra":"secret"}', b'[]', b'\xff',
                     b'{"query":NaN}', b'['*5000):
            with patch('jace.canonical.CanonicalStore', side_effect=AssertionError('no source read')):
                code, out, err, _ = self.invoke(data, '--stdin', '--allow-local-disclosure')
            self.assertEqual(code, 2)
            self.assertEqual(out, '')
            self.assertNotIn('secret', err)
            self.assertNotIn('Traceback', err)

    def test_bounded_read_and_exact_byte_boundary(self):
        base = b'{"query":"x"}'
        data = base + b' '*(65536-len(base))
        code, _, err, read = self.invoke(data, '--stdin','--allow-local-disclosure')
        self.assertEqual(code, 0, err)
        self.assertEqual(read, 65536)
        code, out, _, read = self.invoke(data+b' '*10000, '--stdin','--allow-local-disclosure')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertEqual(read, 65537)

    def test_existing_query_character_limit_still_applies(self):
        data = json.dumps({'query':'x'*10001}).encode()
        with patch('jace.canonical.CanonicalStore', side_effect=AssertionError('no source read')):
            code, out, _, _ = self.invoke(data, '--stdin','--allow-local-disclosure')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')

    def test_real_subprocess_pipe(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, '-m','jace.cli','explain-search','--stdin','--allow-local-disclosure']
        result = subprocess.run(command, input=json.dumps({'query':'करुणा'}).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, cwd=root,
            env=dict(os.environ, PYTHONPATH=str(root/'src'), PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mode'], 'lexical-only')
        self.assertNotIn('करुणा', command)

if __name__ == '__main__': unittest.main()
