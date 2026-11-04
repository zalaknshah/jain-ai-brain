"""Synthetic token configuration and raw loopback header ambiguity regressions."""
import http.client
import json
import socket
import unittest
from unittest.mock import patch

import test_api_authorization as fixture
from jace.auth import ApiAuthorization
from jace.limits import PeerRateLimiter

ALICE = fixture.ALICE_TOKEN
BOB = fixture.BOB_TOKEN
ALLOWED = 'http://127.0.0.1:8080'
DENIED = 'https://other.invalid'


class AuthorizationConfigurationAmbiguityTests(unittest.TestCase):
    def rejected(self, raw):
        with self.assertRaisesRegex(ValueError, '^Invalid API authorization configuration$') as caught:
            ApiAuthorization.from_json(raw)
        for private in (ALICE, BOB, 'alice', 'bob'):
            self.assertNotIn(private, str(caught.exception))

    def test_repeated_token_cannot_choose_owner_by_json_order(self):
        for left, right in [('alice', 'bob'), ('bob', 'alice'), ('alice', 'alice')]:
            with self.subTest(left=left, right=right):
                self.rejected('{' + json.dumps(ALICE) + ':' + json.dumps(left) + ',' + json.dumps(ALICE) + ':' + json.dumps(right) + '}')

    def test_duplicate_cannot_hide_invalid_earlier_or_later_value(self):
        for left, right in [('null', '"alice"'), ('"alice"', 'null'), ('false', '"alice"'), ('{}', '"alice"')]:
            with self.subTest(left=left, right=right):
                self.rejected('{' + json.dumps(ALICE) + ':' + left + ',' + json.dumps(ALICE) + ':' + right + '}')

    def test_escaped_equivalent_token_key_is_also_duplicate(self):
        escaped = '"\\u0074' + ALICE[1:] + '"'
        self.rejected('{' + json.dumps(ALICE) + ':"alice",' + escaped + ':"bob"}')

    def test_unique_tokens_preserve_multiple_credentials_and_case(self):
        token = 'unique-comma-token,' + 'a' * 32
        authorization = ApiAuthorization.from_json(json.dumps({ALICE:'alice', BOB:'bob', token:'alice', ALICE.upper():'upper'}))
        self.assertEqual(authorization.authenticate('Bearer ' + ALICE), 'alice')
        self.assertEqual(authorization.authenticate('bearer ' + BOB), 'bob')
        self.assertEqual(authorization.authenticate('Bearer ' + token), 'alice')
        self.assertEqual(authorization.authenticate('Bearer ' + ALICE.upper()), 'upper')
        self.assertIsNone(authorization.authenticate('Bearer unknown'))

    def test_empty_and_unconfigured_maps_remain_locked(self):
        for raw in ('', '  ', '{}'):
            self.assertFalse(ApiAuthorization.from_json(raw).enabled)


class AuthorizationHeaderAmbiguityTests(unittest.TestCase):
    tearDown = fixture.ApiAuthorizationTests.tearDown

    def setUp(self):
        fixture.ApiAuthorizationTests.setUp(self)
        self.server.rate_limiter = PeerRateLimiter(per_minute=600, burst=100)
        self.memory = self.engine.list_memories('alice')[0]
        self.before = list(self.engine.memory.connection.iterdump())

    def raw(self, method, path, headers=(), body=None):
        data = b'' if body is None else json.dumps(body).encode('utf-8')
        fields = [('Host', 'localhost'), ('Connection', 'close'), *headers]
        if method in ('POST', 'PATCH'):
            fields += [('Content-Type', 'application/json'), ('Content-Length', str(len(data)))]
        wire = (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{name}: {value}\r\n' for name, value in fields) + '\r\n').encode('ascii') + data
        with socket.create_connection(self.server.server_address, timeout=3) as client:
            client.sendall(wire)
            response = http.client.HTTPResponse(client)
            response.begin()
            payload = response.read()
            result = (response.status, response.headers, payload)
            response.close()
            return result

    def assert_rejected(self, result, header):
        status, headers, payload = result
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(payload), {'error': f'at most one {header} header is permitted'})
        self.assertEqual(headers['Connection'], 'close')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        for private in (ALICE.encode(), BOB.encode(), self.memory.content.encode()):
            self.assertNotIn(private, payload)
        if header == 'Origin':
            self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
        self.assertEqual(list(self.engine.memory.connection.iterdump()), self.before)

    def test_authorization_orders_case_and_identical_duplicates_fail_before_admission(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for first, second in [(ALICE, BOB), (BOB, ALICE), (ALICE, 'invalid'), ('invalid', ALICE), (ALICE, ALICE)]:
                with self.subTest(first_is_alice=first == ALICE, second_is_alice=second == ALICE):
                    result = self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + first), ('aUtHoRiZaTiOn', 'Bearer ' + second)])
                    self.assert_rejected(result, 'Authorization')
            admission.assert_not_called()

    def test_origin_orders_case_empty_and_identical_duplicates_never_reflect(self):
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for first, second in [(ALLOWED, DENIED), (DENIED, ALLOWED), (ALLOWED, ALLOWED), ('', ALLOWED), (ALLOWED, '')]:
                with self.subTest(first=first, second=second):
                    result = self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + ALICE), ('Origin', first), ('oRiGiN', second)])
                    self.assert_rejected(result, 'Origin')
            admission.assert_not_called()

    def test_all_mutation_methods_reject_ambiguity_without_database_or_engine_work(self):
        operations = [
            ('POST', '/v1/memory', {'content':'I prefer blue shirts'}, []),
            ('POST', '/v1/think', {'input':'I prefer blue shirts', 'learn':True}, []),
            ('PATCH', '/v1/memory', {'memory_id':self.memory.memory_id, 'content':'I prefer blue shirts'}, []),
            ('PATCH', '/v1/memory-expiration', {'memory_id':self.memory.memory_id, 'expires_at':'2000-01-01T00:00:00Z'}, []),
            ('DELETE', '/v1/memory-item/' + str(self.memory.memory_id), None, [('X-JACE-Confirm-Delete', str(self.memory.memory_id))]),
            ('DELETE', '/v1/memory/alice', None, [('X-JACE-Confirm-Owner-Delete', 'all-memories-graph-and-audit:alice')]),
        ]
        with patch.object(self.engine, 'request_admission', wraps=self.engine.request_admission) as admission:
            for method, path, body, extra in operations:
                for header, duplicate in [('Authorization', [('Authorization', 'Bearer ' + BOB)]), ('Origin', [('Origin', ALLOWED), ('Origin', DENIED)])]:
                    with self.subTest(method=method, path=path, header=header):
                        result = self.raw(method, path, [('Authorization', 'Bearer ' + ALICE), *duplicate, *extra], body)
                        self.assert_rejected(result, header)
            admission.assert_not_called()

    def test_public_health_and_preflight_also_reject_repeated_headers(self):
        for method, path in [('GET', '/health'), ('OPTIONS', '/v1/memory')]:
            for header, fields in [('Authorization', [('Authorization', 'Bearer ' + ALICE), ('Authorization', 'Bearer ' + ALICE)]), ('Origin', [('Origin', ALLOWED), ('Origin', DENIED)])]:
                with self.subTest(method=method, header=header):
                    self.assert_rejected(self.raw(method, path, fields), header)

    def test_singleton_and_absent_headers_preserve_existing_authorization_and_cors(self):
        self.assertEqual(self.raw('GET', '/health')[0], 200)
        self.assertEqual(self.raw('GET', '/v1/memory/alice')[0], 401)
        self.assertEqual(self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + BOB)])[0], 403)
        self.assertEqual(self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + ALICE), ('Origin', DENIED)])[0], 403)
        status, headers, payload = self.raw('GET', '/v1/memory/alice', [('authorization', 'Bearer ' + ALICE), ('origin', ALLOWED)])
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_all('Access-Control-Allow-Origin'), [ALLOWED])
        self.assertIn(self.memory.content, payload.decode())
        status, headers, payload = self.raw('OPTIONS', '/v1/memory', [('Origin', ALLOWED)])
        self.assertEqual(status, 204)
        self.assertEqual(headers.get_all('Access-Control-Allow-Origin'), [ALLOWED])
        self.assertEqual(payload, b'')
        self.assertEqual(list(self.engine.memory.connection.iterdump()), self.before)

    def test_header_values_are_not_split_into_new_credentials(self):
        token = 'comma-containing-token,' + 'a' * 32
        self.server.authorization = ApiAuthorization({token:'alice'})
        status, _, payload = self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + token)])
        self.assertEqual(status, 200)
        self.assertIn(self.memory.content, payload.decode())
        self.assertEqual(self.raw('GET', '/v1/memory/alice', [('Authorization', 'Bearer ' + token + ', Bearer invalid')])[0], 401)


if __name__ == '__main__':
    unittest.main()
