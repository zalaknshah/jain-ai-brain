"""Whole-owner deletion must not silently ignore narrower request selectors."""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

from jace.api import JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner

ALICE = 'synthetic-owner-delete-alice-' + 'a' * 32
BOB = 'synthetic-owner-delete-bob-' + 'b' * 32
OWNER_CONFIRM = ('X-JACE-Confirm-Owner-Delete', 'all-memories-graph-and-audit:alice')


class OwnerDeletionTargetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = CognitiveEngine(db_path=Path(self.directory.name) / 'db.sqlite', reasoner=LocalReasoner())
        self.alice = []
        for scope in ('default', 'home', 'work'):
            memory, _ = self.engine.remember('alice', 'I prefer quiet rooms', memory_scope=scope)
            self.alice.append(memory)
        expired, _ = self.engine.remember('alice', 'I prefer blue clothes', memory_scope='home', expires_at='2000-01-01T00:00:00Z')
        self.alice.append(expired)
        self.bob, _ = self.engine.remember('bob', 'I prefer quiet rooms', memory_scope='home')
        with self.engine.memory.connection:
            for owner in ('alice', 'bob'):
                self.engine.memory.connection.execute("INSERT INTO memory_audit(user_id,content,accepted,reason,created_at) VALUES (?, 'synthetic legacy text', 1, 'legacy', '2020')", (owner,))
        self.server = JaceHTTPServer(('127.0.0.1', 0), self.engine,
            ApiAuthorization({ALICE:'alice', BOB:'bob'}), rate_burst=100)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.before = list(self.engine.memory.connection.iterdump())

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.engine.close(); self.directory.cleanup()

    def delete(self, target='/v1/memory/alice', *, token=ALICE, headers=()):
        fields = [('Host', 'localhost'), ('Connection', 'close'), *headers]
        if token is not None:
            fields.append(('Authorization', 'Bearer ' + token))
        wire = (f'DELETE {target} HTTP/1.1\r\n' + ''.join(f'{name}: {value}\r\n' for name, value in fields) + '\r\n').encode('ascii')
        with socket.create_connection(self.server.server_address, timeout=3) as client:
            client.sendall(wire)
            response = http.client.HTTPResponse(client); response.begin()
            result = response.status, response.headers, json.loads(response.read())
            response.close()
            return result

    def assert_unchanged(self):
        self.assertEqual(list(self.engine.memory.connection.iterdump()), self.before)

    def test_scope_and_other_query_selectors_fail_before_engine_admission(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for query in ('memory_scope=home', 'memory_scope=default', 'memory_scope=home&memory_scope=work',
                          'memory_id=1', 'before_id=2&limit=1', 'user_id=bob', 'unknown=value'):
                with self.subTest(query=query):
                    status, headers, body = self.delete('/v1/memory/alice?' + query, headers=[OWNER_CONFIRM])
                    self.assertEqual(status, 400)
                    self.assertIn('error', body)
                    self.assertEqual(headers['Cache-Control'], 'no-store')
                    self.assert_unchanged()
            admission.assert_not_called()

    def test_empty_delimiters_fragments_parameters_and_absolute_targets_fail(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for target in ('/v1/memory/alice?', '/v1/memory/alice?&', '/v1/memory/alice#home',
                           '/v1/memory/alice#', '/v1/memory/alice;home', '/v1/memory/alice;',
                           'http://localhost/v1/memory/alice'):
                with self.subTest(target=target):
                    self.assertEqual(self.delete(target, headers=[OWNER_CONFIRM])[0], 400)
                    self.assert_unchanged()
            admission.assert_not_called()

    def test_item_confirmation_and_revision_headers_cannot_be_ignored(self):
        item_id, revision = str(self.alice[0].memory_id), self.alice[0].revision
        fields = [('X-JACE-Confirm-Delete', item_id),
                  ('X-JACE-Confirm-Audit-Cleanup', 'all-unattributed-for-owner'),
                  ('X-JACE-If-Memory-Revision', revision)]
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for name, value in fields:
                for choices in ([(name, value)], [(name.lower(), '')], [(name, value), (name.lower(), value)]):
                    with self.subTest(header=name, choices=len(choices), empty=not choices[0][1]):
                        self.assertEqual(self.delete(headers=[OWNER_CONFIRM, *choices])[0], 400)
                        self.assert_unchanged()
            self.assertEqual(self.delete(headers=[OWNER_CONFIRM, *fields])[0], 400)
            self.assert_unchanged()
            admission.assert_not_called()

    def test_plain_owner_target_still_deletes_all_scopes_and_only_that_owner(self):
        connection = self.engine.memory.connection
        bob_before = connection.execute("SELECT * FROM memory_audit WHERE user_id='bob'").fetchall()
        status, _, body = self.delete(headers=[OWNER_CONFIRM])
        self.assertEqual(status, 200)
        self.assertEqual(body, {'deleted':4, 'user_id':'alice'})
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM memories WHERE user_id='alice'").fetchone()[0], 0)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM memory_audit WHERE user_id='alice'").fetchone()[0], 0)
        for memory in self.alice:
            node = f'memory:{memory.memory_id}'
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_nodes WHERE node_id=?', (node,)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_edges WHERE from_id=? OR to_id=?', (node,node)).fetchone()[0], 0)
        self.assertEqual(connection.execute("SELECT * FROM memory_audit WHERE user_id='bob'").fetchall(), bob_before)
        self.assertEqual([item.memory_id for item in self.engine.list_memories('bob', memory_scope='home')], [self.bob.memory_id])
        self.assertEqual(self.delete(headers=[OWNER_CONFIRM])[2], {'deleted':0, 'user_id':'alice'})

    def test_authorization_remains_required_before_any_owner_delete(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for token, status in ((None,401), ('invalid',401), (BOB,403)):
                for target in ('/v1/memory/alice', '/v1/memory/alice?memory_scope=home'):
                    self.assertEqual(self.delete(target, token=token)[0], status)
                    self.assert_unchanged()
            admission.assert_not_called()

    def test_percent_encoded_owner_is_still_bound_to_exact_subject(self):
        owner = 'owner /;? Unicode é'
        self.server.authorization = ApiAuthorization({ALICE:owner, BOB:'bob'})
        memory, _ = self.engine.remember(owner, 'I prefer quiet rooms')
        target = '/v1/memory/' + quote(owner, safe='')
        self.assertEqual(self.delete(target, headers=[('X-JACE-Confirm-Owner-Delete', 'all-memories-graph-and-audit:' + quote(owner, safe=''))])[2], {'deleted':1, 'user_id':owner})
        self.assertEqual([item.memory_id for item in self.engine.list_memories('alice')], [self.alice[0].memory_id])
        self.assertIsNone(self.engine.memory.connection.execute('SELECT id FROM memories WHERE id=?', (memory.memory_id,)).fetchone())

    def test_item_route_retains_its_confirmations_and_revision(self):
        memory = self.alice[0]
        headers = [('X-JACE-Confirm-Delete', str(memory.memory_id)),
                   ('X-JACE-Confirm-Audit-Cleanup', 'all-unattributed-for-owner'),
                   ('X-JACE-If-Memory-Revision', memory.revision)]
        status, _, body = self.delete('/v1/memory-item/' + str(memory.memory_id), headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(body['deleted'], 1)
        remaining = self.engine.memory.connection.execute("SELECT COUNT(*) FROM memories WHERE user_id='alice'").fetchone()[0]
        self.assertEqual(remaining, 3)
        self.assertEqual([item.memory_id for item in self.engine.list_memories('bob', memory_scope='home')], [self.bob.memory_id])


if __name__ == '__main__':
    unittest.main()
