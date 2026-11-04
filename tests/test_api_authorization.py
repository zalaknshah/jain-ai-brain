import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jace.api import JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.engine import CognitiveEngine

ALICE_TOKEN = 'test-alice-' + 'a' * 32
BOB_TOKEN = 'test-bob-' + 'b' * 32


class ApiAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = CognitiveEngine(db_path=Path(self.directory.name) / 'memory.db')
        self.engine.remember('alice', 'I prefer quiet rooms')
        self.server = JaceHTTPServer(('127.0.0.1', 0), self.engine,
                                    ApiAuthorization({ALICE_TOKEN: 'alice', BOB_TOKEN: 'bob'}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.engine.close()
        self.directory.cleanup()

    def request(self, path, method='GET', body=None, token=None, headers=None):
        headers = dict(headers or {})
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        req = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=data, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=2)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}, response.headers

    def test_unauthenticated_memory_read_and_delete_rejected(self):
        self.assertEqual(self.request('/v1/memory/alice')[0], 401)
        self.assertEqual(self.request('/v1/memory/alice', 'DELETE')[0], 401)
        self.assertEqual(len(self.engine.memory.list('alice')), 1)

    def test_wrong_user_cannot_read_write_think_search_or_delete(self):
        for path, method, body in [
            ('/v1/memory/alice', 'GET', None), ('/v1/memory/alice', 'DELETE', None),
            ('/v1/memory', 'POST', {'user_id':'alice','content':'I prefer red'}),
            ('/v1/think', 'POST', {'user_id':'alice','input':'Hello','learn':True}),
            ('/v1/graph/search?q=quiet&user_id=alice', 'GET', None),
        ]:
            with self.subTest(path=path, method=method):
                self.assertEqual(self.request(path, method, body, BOB_TOKEN)[0], 403)
        self.assertEqual(len(self.engine.memory.list('alice')), 1)

    def test_authenticated_subject_is_used_without_client_user_id(self):
        status, body, _ = self.request('/v1/think', 'POST', {'input':'Hello'}, ALICE_TOKEN)
        self.assertEqual(status, 200)
        self.assertEqual(body['user_id'], 'alice')
        self.assertEqual(self.request('/v1/memory/alice', token=ALICE_TOKEN)[0], 200)
        self.assertEqual(self.request('/v1/memory/alice', 'DELETE', token=ALICE_TOKEN, headers={'X-JACE-Confirm-Owner-Delete':'all-memories-graph-and-audit:alice'})[1]['deleted'], 1)

    def test_memory_correction_is_scoped_and_validated(self):
        memory_id = self.engine.list_memories('alice')[0].memory_id
        body = {'memory_id':memory_id,'content':'I prefer gentle movement'}
        self.assertEqual(self.request('/v1/memory','PATCH',body,BOB_TOKEN)[0],404)
        self.assertEqual(self.request('/v1/memory','PATCH',body)[0],401)
        status, corrected, _ = self.request('/v1/memory','PATCH',body,ALICE_TOKEN)
        self.assertEqual(status,200)
        self.assertEqual(corrected['memory']['memory_id'],memory_id)
        self.assertEqual(self.request('/v1/memory','PATCH',{'memory_id':True,'content':'Hello'},ALICE_TOKEN)[0],400)

    def test_unconfigured_server_fails_closed_but_health_works(self):
        self.server.authorization = ApiAuthorization()
        self.assertEqual(self.request('/v1/memory/alice', token=ALICE_TOKEN)[0], 503)
        status, body, _ = self.request('/health')
        self.assertEqual(status, 200)
        self.assertNotIn('graph', body)
        self.assertFalse(body['authorization_configured'])

    def test_wrong_origin_rejected_and_preflight_includes_delete(self):
        self.assertEqual(self.request('/v1/memory/alice', token=ALICE_TOKEN, headers={'Origin':'https://other.invalid'})[0], 403)
        status, _, headers = self.request('/v1/memory/alice', 'OPTIONS', headers={'Origin':'http://127.0.0.1:8080'})
        self.assertEqual(status, 204)
        self.assertIn('DELETE', headers['Access-Control-Allow-Methods'])
        self.assertIn('Authorization', headers['Access-Control-Allow-Headers'])
        self.assertNotEqual(headers['Access-Control-Allow-Origin'], '*')

    def test_invalid_body_is_rejected(self):
        self.assertEqual(self.request('/v1/think', 'POST', [], ALICE_TOKEN)[0], 400)
        self.assertEqual(self.request('/v1/think', 'POST', {'input':None}, ALICE_TOKEN)[0], 400)
        self.assertEqual(self.request('/v1/memory', 'POST', {'content':'x'*70000}, ALICE_TOKEN)[0], 400)

    def test_configuration_errors_do_not_echo_tokens(self):
        for value in ['{', '[]', '{"secret":"alice"}', '{"'+ ALICE_TOKEN +'":null}']:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, '^Invalid API authorization configuration$'):
                    ApiAuthorization.from_json(value)


if __name__ == '__main__':
    unittest.main()
