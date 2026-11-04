import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.memory import MemoryStore
from jace.temporal import eligible_for_recall, normalize_expiration

BEFORE = '2026-12-01T17:59:59.999999+00:00'
BOUNDARY = '2026-12-01T18:00:00.000000+00:00'
AFTER = '2026-12-01T18:00:00.000001+00:00'


class MemoryExpirationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'memory.db'
        self.engine = CognitiveEngine(db_path=self.path)

    def tearDown(self):
        self.engine.close()
        self.directory.cleanup()

    def test_normalizes_offsets_and_rejects_ambiguous_values(self):
        self.assertEqual(normalize_expiration('2026-12-01T23:30:00+05:30'), BOUNDARY)
        self.assertEqual(normalize_expiration('2026-12-01T13:00:00-05:00'), BOUNDARY)
        self.assertEqual(normalize_expiration('2026-12-01T18:00:00Z'), BOUNDARY)
        self.assertIsNone(normalize_expiration(None))
        bad = [True, False, 0, [], {}, '', 'tomorrow', '2026-12-01', '2026-12-01T18:00:00',
               '2026-12-01T18:00:00-00:00', '2026-12-01T18:00:00+05:60',
               '2026-12-01T18:00:00+24:00', '2026-02-30T18:00:00Z',
               '2026-12-01T18:00:60Z', '2026-12-01T18:00:00.1234567Z',
               '9999-12-31T23:59:59-23:00', '0001-01-01T00:00:00+23:00',
               '２０２６-12-01T18:00:00Z']
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.engine.remember('alice', 'quiet temporary room', expires_at=value)
        self.assertEqual(self.engine.list_memories('alice'), [])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0], 0)

    def test_exact_expiry_boundary_in_direct_graph_and_reasoner_context(self):
        memory, _ = self.engine.remember('alice', 'I prefer a quiet room and minimal resources', expires_at=BOUNDARY)
        permanent, _ = self.engine.remember('alice', 'I prefer quiet permanent rooms')
        other, _ = self.engine.remember('bob', 'I prefer quiet private rooms')
        captured = []
        def respond(request, assessment, perspectives, evidence, memories):
            captured.append(memories)
            return 'Use care and ask when uncertain.', None
        with patch.object(self.engine.reasoner, 'respond', side_effect=respond):
            for at, expected in [(BEFORE, True), (BOUNDARY, False), (AFTER, False)]:
                with self.subTest(at=at), patch('jace.engine.recall_time', return_value=at) as clock:
                    result = self.engine.think('alice', 'quiet minimal resources')
                    self.assertEqual(memory.memory_id in [m.memory_id for m in result.memories_used], expected)
                    self.assertEqual(memory.memory_id in [m.memory_id for m in captured[-1]], expected)
                    self.assertNotIn(other.memory_id, [m.memory_id for m in captured[-1]])
                    self.assertEqual(clock.call_count, 1)
                hits = self.engine.graph.retrieve('quiet minimal resources', 'alice', at=at)
                self.assertEqual(f'memory:{memory.memory_id}' in [h.node_id for h in hits], expected)
                self.assertIn(f'memory:{permanent.memory_id}', [h.node_id for h in hits])
                direct = self.engine.memory.search('alice', 'quiet', at=at)
                self.assertEqual(memory.memory_id in [m.memory_id for m in direct], expected)
                self.assertTrue(any(h.node_type == 'canonical' for h in self.engine.graph.retrieve('Ahimsa', 'alice', at=at)))
        # Expiration is not deletion: content and graph remain available for review.
        self.assertEqual(len(self.engine.list_memories('alice')), 2)
        self.assertEqual(self.engine.preview_memory_deletion('alice', memory.memory_id)['memory']['expires_at'], BOUNDARY)
        self.assertIsNotNone(self.engine.memory.connection.execute('SELECT node_id FROM graph_nodes WHERE node_id=?', (f'memory:{memory.memory_id}',)).fetchone())

    def test_no_term_fallback_excludes_expired_and_malformed_stored_rows(self):
        valid, _ = self.engine.remember('alice', 'Permanent travel preference')
        expired, _ = self.engine.remember('alice', 'Expired travel preference', expires_at=BOUNDARY)
        broken, _ = self.engine.remember('alice', 'Malformed travel preference')
        for invalid in ['garbage', '9999-99-99T00:00:00Z', 123, b'blob']:
            self.engine.memory.connection.execute('UPDATE memories SET expires_at=? WHERE id=?', (invalid, broken.memory_id))
            self.engine.memory.connection.commit()
            self.assertEqual([m.memory_id for m in self.engine.memory.search('alice', '12345', at=AFTER)], [valid.memory_id])
            hits = self.engine.graph.retrieve('travel', 'alice', at=AFTER)
            self.assertEqual([h.source_id for h in hits if h.node_type == 'memory'], [str(valid.memory_id)])
        self.assertFalse(eligible_for_recall(BOUNDARY, BOUNDARY))
        self.assertEqual(len(self.engine.list_memories('alice')), 3)

    def test_expired_rows_do_not_hide_older_active_memories(self):
        valid, _ = self.engine.remember('alice', 'I prefer a quiet room')
        for _ in range(105):
            self.engine.remember('alice', 'I prefer a quiet room temporarily', expires_at=BOUNDARY)
        self.assertEqual([m.memory_id for m in self.engine.memory.search('alice', 'quiet', at=AFTER)], [valid.memory_id])

    def test_change_is_owned_explicit_and_correction_never_renews(self):
        original, _ = self.engine.remember('alice', 'I prefer a quiet room')
        self.assertIsNone(original.expires_at)
        changed = self.engine.set_memory_expiration('alice', original.memory_id, '2026-12-01T23:30:00+05:30')
        self.assertEqual(changed.expires_at, BOUNDARY)
        self.assertEqual(changed.created_at, original.created_at)
        corrected, _ = self.engine.correct_memory('alice', original.memory_id, 'I prefer a quiet garden')
        self.assertEqual(corrected.expires_at, BOUNDARY)
        self.assertEqual(self.engine.memory.search('alice', 'quiet', at=AFTER), [])
        for owner, memory_id in [('bob', original.memory_id), ('alice', original.memory_id + 1)]:
            with self.assertRaises(LookupError):
                self.engine.set_memory_expiration(owner, memory_id, None)
        for bad_id in [True, False, 0, -1, 2**63, '1']:
            with self.assertRaises(ValueError):
                self.engine.set_memory_expiration('alice', bad_id, None)
        with self.assertRaises(ValueError):
            self.engine.set_memory_expiration('', original.memory_id, None)
        renewed = self.engine.set_memory_expiration('alice', original.memory_id, None)
        self.assertIsNone(renewed.expires_at)
        self.assertEqual([m.memory_id for m in self.engine.memory.search('alice', 'quiet', at=AFTER)], [original.memory_id])
        self.assertEqual([h.source_id for h in self.engine.graph.retrieve('quiet', 'alice', at=AFTER) if h.node_type == 'memory'], [str(original.memory_id)])
        rows = self.engine.memory.connection.execute('SELECT content,memory_id FROM memory_audit WHERE user_id=?', ('alice',)).fetchall()
        self.assertTrue(all(r['content'] is None and r['memory_id'] == original.memory_id for r in rows))

    def test_audit_failure_rolls_back_expiry_without_graph_drift(self):
        memory, _ = self.engine.remember('alice', 'I prefer quiet rooms')
        connection = self.engine.memory.connection
        old = tuple(connection.execute('SELECT * FROM memories').fetchone())
        connection.execute("CREATE TRIGGER fail_expiry_audit BEFORE INSERT ON memory_audit BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END")
        connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.engine.set_memory_expiration('alice', memory.memory_id, BOUNDARY)
        self.assertEqual(tuple(connection.execute('SELECT * FROM memories').fetchone()), old)
        self.assertEqual([h.source_id for h in self.engine.graph.retrieve('quiet', 'alice', at=AFTER) if h.node_type == 'memory'], [str(memory.memory_id)])
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0], 1)

    def test_concurrent_correction_preserves_expiry_with_two_engines(self):
        memory, _ = self.engine.remember('alice', 'I prefer quiet rooms')
        other = CognitiveEngine(db_path=self.path)
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        errors = []
        original = self.engine.memory.set_expiration
        def paused(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test timed out')
            return result
        def expire():
            try:
                self.engine.set_memory_expiration('alice', memory.memory_id, BOUNDARY)
            except Exception as error:
                errors.append(error)
        def correct():
            try:
                other.correct_memory('alice', memory.memory_id, 'I prefer quiet gardens')
            except Exception as error:
                errors.append(error)
            finally:
                done.set()
        try:
            with patch.object(self.engine.memory, 'set_expiration', side_effect=paused):
                first = threading.Thread(target=expire); first.start()
                self.assertTrue(entered.wait(2))
                second = threading.Thread(target=correct); second.start()
                self.assertFalse(done.wait(.1))
                release.set(); first.join(3); second.join(3)
            self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive()); self.assertEqual(errors, [])
            stored = other.list_memories('alice')[0]
            self.assertEqual(stored.expires_at, BOUNDARY)
            self.assertEqual(stored.content, 'I prefer quiet gardens')
            self.assertEqual(other.memory.search('alice', 'quiet', at=AFTER), [])
            self.assertEqual([h for h in other.graph.retrieve('quiet', 'alice', at=AFTER) if h.node_type == 'memory'], [])
        finally:
            release.set()
            other.close()

    def test_old_schema_migration_preserves_permanent_rows_and_audits(self):
        path = Path(self.directory.name) / 'old.db'
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE memories(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'user')")
            connection.execute("INSERT INTO memories(user_id,content,created_at) VALUES ('alice','Original preference','2026-01-01')")
        store = MemoryStore(path)
        try:
            self.assertIsNone(store.list('alice')[0].expires_at)
            self.assertEqual(store.search('alice', 'preference', at=AFTER)[0].content, 'Original preference')
        finally:
            store.close()
        reopened = MemoryStore(path)
        try:
            self.assertEqual(len(reopened.list('alice')), 1)
        finally:
            reopened.close()

    def test_failed_schema_migration_rolls_back_added_columns(self):
        path = Path(self.directory.name) / 'migration-failure.db'
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE memories(id INTEGER PRIMARY KEY,user_id TEXT,content TEXT,created_at TEXT,source TEXT)")
            connection.execute("INSERT INTO memories VALUES (1, 'alice', 'Existing quiet preference', '2026-01-01', 'user')")
        connect = sqlite3.connect
        opened = []
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql.startswith('CREATE INDEX IF NOT EXISTS memory_audit_owner_item'):
                    raise sqlite3.OperationalError('injected schema failure')
                return super().execute(sql, *args, **kwargs)
        def failing_connect(*args, **kwargs):
            result = connect(*args, factory=FailingConnection, **kwargs)
            opened.append(result)
            return result
        try:
            with patch('jace.memory.sqlite3.connect', side_effect=failing_connect):
                with self.assertRaises(sqlite3.OperationalError):
                    MemoryStore(path)
        finally:
            for connection in opened:
                connection.close()
        with connect(path) as connection:
            columns = {r[1] for r in connection.execute('PRAGMA table_info(memories)')}
            self.assertNotIn('expires_at', columns)
            self.assertNotIn('updated_at', columns)
            self.assertEqual(connection.execute('SELECT content FROM memories').fetchone()[0], 'Existing quiet preference')
        store = MemoryStore(path)
        try:
            self.assertIsNone(store.list('alice')[0].expires_at)
        finally:
            store.close()

    def test_expired_memory_can_still_be_deleted_with_original_confirmation_rules(self):
        memory, _ = self.engine.remember('alice', 'Temporary room preference', expires_at=BOUNDARY)
        self.assertEqual(self.engine.forget_memory('alice', memory.memory_id, confirm_delete=True), 1)
        self.assertEqual(self.engine.list_memories('alice'), [])

    def test_cli_creation_update_and_explicit_removal(self):
        env = dict(os.environ, JACE_DB_PATH=str(self.path), PYTHONPATH='src')
        env.pop('JACE_REASONER_URL', None)
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'jace.cli', *args], env=env, capture_output=True, text=True, timeout=5)
        result = cli('remember', 'alice', 'Temporary quiet preference', '--expires-at', BOUNDARY)
        self.assertEqual(result.returncode, 0, result.stderr)
        memory = json.loads(result.stdout)['memory']
        self.assertEqual(memory['expires_at'], BOUNDARY)
        self.assertNotEqual(cli('set-memory-expiration', 'alice', str(memory['memory_id'])).returncode, 0)
        self.assertNotEqual(cli('set-memory-expiration', 'bob', str(memory['memory_id']), '--never').returncode, 0)
        self.assertNotEqual(cli('set-memory-expiration', 'alice', str(memory['memory_id']), '--at', 'tomorrow').returncode, 0)
        result = cli('set-memory-expiration', 'alice', str(memory['memory_id']), '--never')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(result.stdout)['memory']['expires_at'])


class MemoryExpirationHTTPTests(unittest.TestCase):
    setUp = api_fixture.ApiAuthorizationTests.setUp
    tearDown = api_fixture.ApiAuthorizationTests.tearDown
    request = api_fixture.ApiAuthorizationTests.request

    def test_owned_expiry_creation_change_read_and_auth(self):
        status, body, _ = self.request('/v1/memory', 'POST', {'content': 'Quiet temporary room', 'expires_at': BOUNDARY}, api_fixture.ALICE_TOKEN)
        self.assertEqual(status, 201)
        mid = body['memory']['memory_id']
        self.assertEqual(body['memory']['expires_at'], BOUNDARY)
        body = {'memory_id': mid, 'expires_at': None}
        self.assertEqual(self.request('/v1/memory-expiration', 'PATCH', body)[0], 401)
        self.assertEqual(self.request('/v1/memory-expiration', 'PATCH', body, api_fixture.BOB_TOKEN)[0], 404)
        body['user_id'] = 'alice'
        self.assertEqual(self.request('/v1/memory-expiration', 'PATCH', body, api_fixture.BOB_TOKEN)[0], 403)
        status, result, _ = self.request('/v1/memory-expiration', 'PATCH', body, api_fixture.ALICE_TOKEN)
        self.assertEqual(status, 200)
        self.assertIsNone(result['memory']['expires_at'])
        status, result, _ = self.request(f'/v1/memory-item/{mid}', token=api_fixture.ALICE_TOKEN)
        self.assertEqual(status, 200)
        self.assertIsNone(result['memory']['expires_at'])

    def test_missing_invalid_and_ambiguous_requests_leave_memory_unchanged(self):
        original = self.engine.list_memories('alice')[0]
        for body in [{'memory_id': original.memory_id}, {'memory_id': original.memory_id, 'expires_at': True},
                     {'memory_id': original.memory_id, 'expires_at': '2026-12-01'},
                     {'memory_id': True, 'expires_at': BOUNDARY}]:
            self.assertEqual(self.request('/v1/memory-expiration', 'PATCH', body, api_fixture.ALICE_TOKEN)[0], 400)
        for path in ['/v1/memory-expiration?', '/v1/memory-expiration;anything', '/v1/memory-expiration/']:
            self.assertEqual(self.request(path, 'PATCH', {'memory_id': original.memory_id, 'expires_at': BOUNDARY}, api_fixture.ALICE_TOKEN)[0], 404)
        self.assertEqual(self.request('/v1/memory', 'POST', {'content': 'quiet', 'expires_at': 'invalid'}, api_fixture.ALICE_TOKEN)[0], 400)
        self.assertEqual(self.engine.list_memories('alice'), [original])


if __name__ == '__main__':
    unittest.main()
