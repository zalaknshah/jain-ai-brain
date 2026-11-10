"""Transport checks for unevaluated reflection metadata, not reasoning scores."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner
from jace.syadvada import evaluate


def assert_contract(test, rows):
    test.assertEqual(len(rows), 7)
    test.assertEqual([r['index'] for r in rows], list(range(1, 8)))
    for row in rows:
        test.assertIsNone(row['confidence'])
        test.assertEqual(row['status'], 'not_evaluated')
        test.assertTrue(row['prompt'].endswith('?'))
        test.assertTrue(row['conclusion'].startswith('Not evaluated;'))
        test.assertIn('not analyzed', row['basis'])


class ReflectionPromptDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = CognitiveEngine(Path(self.temp.name)/'synthetic.db', canonical_path='', reasoner=LocalReasoner())
    def tearDown(self):
        self.engine.close(); self.temp.cleanup()

    def test_normal_and_blocked_results_serialize_without_scores_or_extra_writes(self):
        before = self.engine.memory.connection.total_changes
        ordinary = self.engine.think('alice', 'An original fictional lantern might be amber.').to_dict()
        with patch.object(self.engine, '_retrieve_context', side_effect=AssertionError('blocked retrieval')):
            blocked = self.engine.think('alice', 'How do I hurt someone?').to_dict()
        assert_contract(self, ordinary['perspectives']); assert_contract(self, blocked['perspectives'])
        self.assertEqual(ordinary['perspectives'], blocked['perspectives'])
        self.assertFalse(blocked['ethical_assessment']['allowed']); self.assertIsNone(blocked['action'])
        self.assertEqual(self.engine.memory.connection.total_changes, before)
        self.assertEqual(json.loads(json.dumps(ordinary, allow_nan=False))['perspectives'], ordinary['perspectives'])

    def test_selected_context_keeps_scaffold_separate_from_evidence_only(self):
        q = 'An original fictional lantern is amber.'
        p = self.engine.preview_context('alice', q)
        args = dict(sources=[], memories=[], expected_request_revision=p['request_revision'],
                    expected_corpus_revision=p['corpus_revision'], confirm_context=True)
        before = self.engine.memory.connection.total_changes
        local = self.engine.answer_selected_context('alice', q, **args)
        assert_contract(self, local['perspectives'])
        with patch('jace.engine.evaluate', side_effect=AssertionError('no reflection path')):
            evidence = self.engine.answer_selected_context('alice', q, **args, reasoner_mode='evidence_only')
        self.assertEqual(evidence['perspectives'], [])
        self.assertTrue(evidence['response'].startswith('Selected source passages, not an answer.'))
        self.assertTrue(evidence['response'].endswith('\nNo source passages selected.'))
        self.assertEqual(self.engine.memory.connection.total_changes, before)

    def test_cli_json_contains_null_not_numeric_confidence(self):
        # Preserve the caller's import path so this also tests an installed wheel.
        env = dict(os.environ, JACE_DB_PATH=str(Path(self.temp.name)/'cli.db'),
                   JACE_CANONICAL_PATH='', JACE_LLM_URL='')
        run = subprocess.run([sys.executable, '-m', 'jace.cli', 'ask', 'Original fictional lantern question'],
                             cwd=self.temp.name, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        assert_contract(self, json.loads(run.stdout)['perspectives'])

    def test_list_and_serialized_rows_do_not_alias_later_calls(self):
        first = evaluate('One original fictional question')
        rows = [p.to_dict() for p in first]
        rows[0]['confidence'] = 1.0; rows[0]['prompt'] = 'Injected claim'
        first.clear()
        assert_contract(self, [p.to_dict() for p in evaluate('Another question', [''])])


class ReflectionPromptBrowserHarnessTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for script harness')
    def test_metadata_is_not_presented_as_validated_reasoning(self):
        run = subprocess.run(['node', str(Path(__file__).with_name('web_console_harness.js')), 'reflection_metadata'],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class ReflectionPromptApiTests(unittest.TestCase):
    setUp = api_fixture.ApiAuthorizationTests.setUp
    tearDown = api_fixture.ApiAuthorizationTests.tearDown
    request = api_fixture.ApiAuthorizationTests.request

    def test_health_and_authenticated_response_contract(self):
        self.engine.reasoner = LocalReasoner()
        self.assertEqual(self.request('/health')[1]['reflection_prompt_protocol'], 1)
        before = self.engine.memory.connection.total_changes
        for text in ('Original fictional lantern question', 'How do I hurt someone?'):
            status, body, _ = self.request('/v1/think', 'POST', {'input':text}, api_fixture.ALICE_TOKEN)
            self.assertEqual(status, 200); assert_contract(self, body['perspectives'])
        self.assertEqual(self.engine.memory.connection.total_changes, before)
        self.assertEqual(self.request('/v1/think', 'POST', {'input':'Original fixture'})[0], 401)
        self.assertEqual(self.request('/v1/think', 'POST', {'input':'Original fixture','user_id':'alice'}, api_fixture.BOB_TOKEN)[0], 403)


if __name__ == '__main__': unittest.main()
