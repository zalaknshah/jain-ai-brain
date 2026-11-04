import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from jace.engine import CognitiveEngine
from jace.memory import MemoryDeletionConsentRequired
import test_api_authorization as api_fixture
from test_api_authorization import ALICE_TOKEN, BOB_TOKEN

ROOT = Path(__file__).resolve().parents[1]


class MemoryDeletionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'db.sqlite'
        self.engine = CognitiveEngine(db_path=self.path)
        self.first, _ = self.engine.remember('alice', 'I prefer blue cloth')
        self.second, _ = self.engine.remember('alice', 'I prefer quiet rooms')
        self.bob, _ = self.engine.remember('bob', 'I prefer quiet rooms')

    def tearDown(self):
        self.engine.close(); self.directory.cleanup()

    def snapshot(self):
        with sqlite3.connect(self.path) as connection:
            return [connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                    for table in ('memories', 'memory_audit', 'graph_nodes', 'graph_edges')]

    def add_legacy(self, owner='alice', content='historical private fixture'):
        with sqlite3.connect(self.path) as connection:
            connection.execute("INSERT INTO memory_audit(user_id,content,accepted,reason,created_at) VALUES (?,?,1,'legacy','2020-01-01')", (owner, content))

    def test_owner_and_explicit_confirmation_are_both_required(self):
        before = self.snapshot()
        for actor, memory_id, options, error in (
            ('alice', self.first.memory_id, {}, ValueError),
            ('alice', self.first.memory_id, {'confirm_delete': 'true'}, ValueError),
            ('alice', self.first.memory_id, {'confirm_delete': True, 'confirm_unattributed_audit_cleanup': 1}, ValueError),
            ('bob', self.first.memory_id, {'confirm_delete': True}, LookupError),
            ('alice', True, {'confirm_delete': True}, ValueError),
            ('alice', 10**1000, {'confirm_delete': True}, ValueError),
        ):
            with self.subTest(actor=actor, memory_id=memory_id), self.assertRaises(error):
                self.engine.forget_memory(actor, memory_id, **options)
        with self.assertRaises(LookupError):
            self.engine.preview_memory_deletion('bob', self.first.memory_id)
        self.assertEqual(self.snapshot(), before)

    def test_deletion_preserves_other_memories_and_removes_linked_history(self):
        self.engine.correct_memory('alice', self.first.memory_id, 'I prefer red cloth')
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit WHERE memory_id=?', (self.first.memory_id,)).fetchone()[0], 2)
        self.assertEqual(self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True), 1)
        self.assertEqual([m.memory_id for m in self.engine.list_memories('alice')], [self.second.memory_id])
        self.assertEqual([m.memory_id for m in self.engine.list_memories('bob')], [self.bob.memory_id])
        with sqlite3.connect(self.path) as connection:
            node = f'memory:{self.first.memory_id}'
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit WHERE memory_id=?', (self.first.memory_id,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_nodes WHERE node_id=?', (node,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_edges WHERE from_id=? OR to_id=?', (node, node)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0], 2)
        with self.assertRaises(LookupError):
            self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True)

    def test_legacy_cleanup_is_disclosed_and_requires_its_own_choice(self):
        self.add_legacy(); self.add_legacy('bob')
        preview = self.engine.preview_memory_deletion('alice', self.first.memory_id)
        self.assertEqual(preview['unattributed_audit_entries'], 1)
        self.assertIn('all 1 unattributed audit entries', preview['warning'])
        before = self.snapshot()
        with self.assertRaises(MemoryDeletionConsentRequired):
            self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True)
        self.assertEqual(before, self.snapshot())
        self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True, confirm_unattributed_audit_cleanup=True)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memory_audit WHERE user_id='alice' AND memory_id IS NULL").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memory_audit WHERE user_id='bob' AND memory_id IS NULL").fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit WHERE memory_id=?', (self.second.memory_id,)).fetchone()[0], 1)

    def test_new_unattributed_audit_after_preview_requires_confirmation_at_delete(self):
        preview = self.engine.preview_memory_deletion('alice', self.first.memory_id)
        self.assertFalse(preview['requires_unattributed_audit_cleanup_confirmation'])
        self.add_legacy()
        with self.assertRaises(MemoryDeletionConsentRequired):
            self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True)
        self.assertEqual(len(self.engine.list_memories('alice')), 2)

    def test_stale_deleted_item_cannot_trigger_unrelated_audit_cleanup(self):
        self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True)
        self.add_legacy()
        before = self.snapshot()
        with self.assertRaises(LookupError):
            self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True,
                                      confirm_unattributed_audit_cleanup=True)
        self.assertEqual(before, self.snapshot())

    def test_failure_after_graph_deletion_rolls_back_memory_audit_and_edges(self):
        self.add_legacy(); before = self.snapshot()
        original = self.engine.graph.remove_memories
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('injected failure after graph mutation')
        with patch.object(self.engine.graph, 'remove_memories', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True, confirm_unattributed_audit_cleanup=True)
        self.assertEqual(before, self.snapshot())

    def concurrent_delete(self, separate_engine, correction):
        other = CognitiveEngine(db_path=self.path) if separate_engine else self.engine
        paused, resume, started, done = (threading.Event() for _ in range(4))
        errors, outcome = [], {}
        original = self.engine.memory.delete_one
        def pause(*args, **kwargs):
            result = original(*args, **kwargs); paused.set()
            if not resume.wait(3): raise RuntimeError('coordination timeout')
            return result
        def deletion():
            try: outcome['deleted'] = self.engine.forget_memory('alice', self.first.memory_id, confirm_delete=True)
            except Exception as error: errors.append(error)
        def concurrent_write():
            started.set()
            try:
                if correction:
                    other.correct_memory('alice', self.first.memory_id, 'I prefer green cloth')
                    errors.append(AssertionError('correction resurrected deleted memory'))
                else:
                    outcome['new'], _ = other.remember('alice', 'I prefer green cloth')
            except LookupError:
                if not correction: errors.append(AssertionError('unexpected lookup failure'))
                outcome['not_found'] = True
            except Exception as error: errors.append(error)
            finally: done.set()
        a, b = threading.Thread(target=deletion), threading.Thread(target=concurrent_write)
        try:
            with patch.object(self.engine.memory, 'delete_one', side_effect=pause):
                a.start(); self.assertTrue(paused.wait(2)); b.start(); self.assertTrue(started.wait(2))
                self.assertFalse(done.wait(.1)); resume.set(); a.join(3); b.join(3)
            self.assertFalse(a.is_alive() or b.is_alive()); self.assertEqual(errors, [])
            self.assertEqual(outcome['deleted'], 1)
            self.assertEqual(len(self.engine.list_memories('alice')), 1 if correction else 2)
            if correction: self.assertTrue(outcome['not_found'])
            with sqlite3.connect(self.path) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes g LEFT JOIN memories m ON g.node_id='memory:'||m.id WHERE g.node_type='memory' AND m.id IS NULL").fetchone()[0], 0)
        finally:
            resume.set()
            if a.ident: a.join(3)
            if b.ident: b.join(3)
            if other is not self.engine: other.close()

    def test_one_engine_serializes_correction_against_deletion(self): self.concurrent_delete(False, True)
    def test_two_engines_cannot_resurrect_deleted_memory(self): self.concurrent_delete(True, True)
    def test_new_memory_after_deletion_is_preserved(self): self.concurrent_delete(True, False)

    def test_cli_previews_before_deletion_and_legacy_cleanup_is_separate(self):
        self.add_legacy()
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), JACE_DB_PATH=str(self.path))
        command = [sys.executable, '-m', 'jace.cli', 'forget-memory', 'alice', str(self.first.memory_id)]
        preview = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(preview.stdout)['deleted'], 0)
        self.assertIn('all 1 unattributed audit entries', json.loads(preview.stdout)['warning'])
        refused = subprocess.run([*command, '--confirm-delete'], env=env, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2); self.assertEqual(len(self.engine.list_memories('alice')), 2)
        accepted = subprocess.run([*command, '--confirm-delete', '--confirm-all-unattributed-audit-cleanup'], env=env, cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(accepted.stdout)['deleted'], 1)

    def test_legacy_audit_schema_migrates_without_guessing_association(self):
        path = Path(self.directory.name) / 'legacy.sqlite'
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE memory_audit(id INTEGER PRIMARY KEY,user_id TEXT,content TEXT,accepted INTEGER,reason TEXT,created_at TEXT)')
            connection.execute("INSERT INTO memory_audit VALUES (1,'alice','legacy text',1,'accepted','2020')")
        engine = CognitiveEngine(db_path=path)
        try:
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute('SELECT content,memory_id FROM memory_audit').fetchone(), ('legacy text', None))
        finally: engine.close()


class ItemDeletionApiTests(unittest.TestCase):
    setUp = api_fixture.ApiAuthorizationTests.setUp
    tearDown = api_fixture.ApiAuthorizationTests.tearDown
    request = api_fixture.ApiAuthorizationTests.request

    def test_authenticated_item_preview_and_confirmation(self):
        memory = self.engine.list_memories('alice')[0]; path = f'/v1/memory-item/{memory.memory_id}'
        headers = {'X-JACE-Confirm-Delete': str(memory.memory_id)}
        self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.request(path, token=BOB_TOKEN)[0], 404)
        self.assertEqual(self.request(path, token=ALICE_TOKEN)[1]['memory']['memory_id'], memory.memory_id)
        self.assertEqual(self.request(path, 'DELETE', token=ALICE_TOKEN)[0], 409)
        self.assertEqual(self.request(path, 'DELETE', token=BOB_TOKEN, headers=headers)[0], 404)
        self.assertEqual(self.request(path, 'DELETE', token=ALICE_TOKEN, headers={'X-JACE-Confirm-Delete':'999'})[0], 409)
        self.assertEqual(self.request(path, 'DELETE', token=ALICE_TOKEN, headers=headers)[1]['deleted'], 1)
        self.assertEqual(self.request(path, token=ALICE_TOKEN)[0], 404)

    def test_legacy_cleanup_conflict_then_explicit_confirmation(self):
        memory = self.engine.list_memories('alice')[0]; path = f'/v1/memory-item/{memory.memory_id}'
        with sqlite3.connect(self.engine.memory.db_path) as connection:
            connection.execute("INSERT INTO memory_audit(user_id,content,accepted,reason,created_at) VALUES ('alice','legacy text',1,'old','2020')")
        headers = {'X-JACE-Confirm-Delete':str(memory.memory_id)}
        status, body, _ = self.request(path, 'DELETE', token=ALICE_TOKEN, headers=headers)
        self.assertEqual(status, 409); self.assertIn('all 1 unattributed', body['error'])
        self.assertEqual(len(self.engine.list_memories('alice')), 1)
        headers['X-JACE-Confirm-Audit-Cleanup'] = 'all-unattributed-for-owner'
        self.assertEqual(self.request(path, 'DELETE', token=ALICE_TOKEN, headers=headers)[0], 200)

    def test_invalid_id_query_body_and_duplicate_confirmation_fail_closed(self):
        memory = self.engine.list_memories('alice')[0]
        for suffix in ['0','-1','01','1/2','%31',str(2**63),'1?user_id=bob','1;anything','1;','1?']:
            self.assertEqual(self.request('/v1/memory-item/'+suffix, 'DELETE', token=ALICE_TOKEN)[0], 400)
        self.assertEqual(self.request('/v1/memory-item/1;anything', token=ALICE_TOKEN)[0], 400)
        for extra in [f'X-JACE-Confirm-Delete: {memory.memory_id}\r\n',
                      'X-JACE-Confirm-Audit-Cleanup: all-unattributed-for-owner\r\nX-JACE-Confirm-Audit-Cleanup: all-unattributed-for-owner\r\n',
                      'X-JACE-Confirm-Audit-Cleanup: no\r\n',
                      'Content-Length: 1\r\n', 'Content-Length: 0\r\nContent-Length: 99\r\nTransfer-Encoding: chunked\r\n']:
            with socket.create_connection(self.server.server_address, timeout=2) as connection:
                request = (f'DELETE /v1/memory-item/{memory.memory_id} HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {ALICE_TOKEN}\r\nX-JACE-Confirm-Delete: {memory.memory_id}\r\n'+extra+'\r\n')
                connection.sendall(request.encode()); reply = connection.recv(4096)
                self.assertTrue(b' 400 ' in reply or b' 409 ' in reply, reply)
        self.assertEqual(len(self.engine.list_memories('alice')), 1)
