import json
import socket
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jace.api import JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.engine import CognitiveEngine
from jace.limits import PeerRateLimiter

TOKEN = 'test-service-limits-' + 'x' * 32


@contextmanager
def running_server(**options):
    with tempfile.TemporaryDirectory() as directory:
        engine = CognitiveEngine(db_path=Path(directory) / 'db')
        server = JaceHTTPServer(('127.0.0.1', 0), engine, ApiAuthorization({TOKEN:'alice'}), **options)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':0.01})
        thread.start()
        try:
            yield server, engine
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            engine.close()


def get(server, path='/health', headers=None):
    try:
        result = urlopen(Request(f'http://127.0.0.1:{server.server_port}{path}', headers=headers or {}), timeout=2)
    except HTTPError as error:
        result = error
    with result:
        result.read()
        return result.status, result.headers


class RateLimiterTests(unittest.TestCase):
    def test_burst_refill_and_separate_peers(self):
        clock = [0.0]
        limiter = PeerRateLimiter(per_minute=60, burst=2, clock=lambda: clock[0])
        self.assertTrue(limiter.allow('a')[0]); self.assertTrue(limiter.allow('a')[0])
        self.assertEqual(limiter.allow('a'), (False, 1))
        self.assertTrue(limiter.allow('b')[0])
        clock[0] = 1.0
        self.assertTrue(limiter.allow('a')[0])
        self.assertFalse(limiter.allow('a')[0])

    def test_accounting_is_bounded_and_only_idle_full_buckets_expire(self):
        clock = [0.0]
        limiter = PeerRateLimiter(burst=1, max_clients=2, clock=lambda: clock[0])
        limiter.allow('a'); limiter.allow('b')
        self.assertFalse(limiter.allow('c')[0])
        self.assertEqual(len(limiter._buckets), 2)
        clock[0] = 61.0
        self.assertTrue(limiter.allow('c')[0])
        self.assertEqual(len(limiter._buckets), 1)

    def test_invalid_limits_fail_closed(self):
        for options in ({'per_minute':0}, {'burst':False}, {'max_clients':10001}):
            with self.assertRaises(ValueError):
                PeerRateLimiter(**options)
        for options in ({'request_timeout':float('nan')}, {'request_timeout':0}, {'request_timeout':True}, {'max_connections':0}):
            with self.assertRaises(ValueError):
                JaceHTTPServer(('127.0.0.1',0), None, **options)


class ServiceLimitsTests(unittest.TestCase):
    def test_rate_limit_includes_public_requests_and_ignores_forwarded_headers(self):
        with running_server(rate_burst=2, rate_per_minute=1) as (server, _):
            self.assertEqual(get(server)[0],200)
            self.assertEqual(get(server)[0],200)
            status, headers = get(server, headers={'X-Forwarded-For':'203.0.113.77'})
            self.assertEqual(status,429)
            self.assertGreaterEqual(int(headers['Retry-After']),1)
            self.assertEqual(headers['Connection'],'close')

    def test_target_and_headers_are_bounded_before_work(self):
        with running_server() as (server, engine):
            self.assertEqual(get(server, '/health?' + 'x'*8192)[0],414)
            self.assertEqual(get(server, headers={'X-Large':'x'*17000})[0],431)
            self.assertEqual(engine.list_memories('alice'),[])

    def test_connection_capacity_is_released_after_partial_header_deadline(self):
        with running_server(max_connections=1, request_timeout=0.2) as (server, _):
            first = socket.create_connection(server.server_address, timeout=2)
            try:
                first.sendall(b'GET /health HTTP/1.1\r\nHost: localhost\r\n')
                deadline = time.monotonic() + 1
                while server._connection_slots._value != 0 and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertEqual(server._connection_slots._value,0)
                self.assertEqual(get(server)[0],503)
                self.assertEqual(first.recv(4096), b'')
            finally:
                first.close()
            deadline = time.monotonic()+1
            while server._connection_slots._value != 1 and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(get(server)[0],200)

    def test_partial_body_deadline_does_not_persist(self):
        with running_server(request_timeout=0.2) as (server, engine):
            with socket.create_connection(server.server_address, timeout=2) as client:
                header = f'POST /v1/memory HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n'
                client.sendall(header.encode() + b'{"content":"')
                self.assertEqual(client.recv(4096), b'')
            self.assertEqual(engine.list_memories('alice'),[])
            self.assertEqual(get(server)[0],200)

    def test_slow_drip_headers_do_not_extend_absolute_read_deadline(self):
        with running_server(request_timeout=0.15) as (server, _):
            with socket.create_connection(server.server_address, timeout=2) as client:
                client.sendall(b'GET /health HTTP/1.1\r\nX-Slow: ')
                started = time.monotonic()
                for _ in range(8):
                    try:
                        client.sendall(b'x')
                    except OSError:
                        break
                    time.sleep(0.04)
                self.assertEqual(client.recv(4096), b'')
                self.assertLess(time.monotonic() - started, 1.0)
            self.assertEqual(get(server)[0],200)

    def test_read_deadline_stops_before_application_work_not_mid_write(self):
        with running_server(request_timeout=0.1) as (server, engine):
            from jace.reasoner import LocalReasoner
            class SlowFixture(LocalReasoner):
                def respond(self, *args):
                    time.sleep(0.2)
                    return super().respond(*args)
            engine.reasoner = SlowFixture()
            request = Request(f'http://127.0.0.1:{server.server_port}/v1/think',
                              data=json.dumps({'input':'Hello'}).encode(),
                              headers={'Content-Type':'application/json','Authorization':'Bearer '+TOKEN})
            with urlopen(request, timeout=2) as response:
                self.assertEqual(response.status,200)
                self.assertEqual(json.load(response)['user_id'],'alice')

    def test_invalid_framing_cannot_execute_delete_or_other_bodyless_handlers(self):
        with running_server() as (server, engine):
            engine.remember('alice', 'I prefer quiet rooms')
            for method, path in [('DELETE','/v1/memory/alice'), ('GET','/health'), ('OPTIONS','/v1/memory')]:
                for framing in ('Content-Length: 0\r\nContent-Length: 99\r\nTransfer-Encoding: chunked',
                                'Content-Length: 1', 'Transfer-Encoding: chunked', 'Content-Length: 0\r\nContent-Length: 0'):
                    with self.subTest(method=method, framing=framing):
                        with socket.create_connection(server.server_address, timeout=2) as client:
                            header = f'{method} {path} HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\n{framing}\r\n\r\n'
                            client.sendall(header.encode())
                            self.assertIn(b' 400 ', client.recv(4096).split(b'\r\n')[0])
                        self.assertEqual(len(engine.list_memories('alice')),1)

    def test_duplicate_lengths_and_transfer_encoding_are_rejected(self):
        with running_server() as (server, engine):
            for framing in ('Content-Length: 2\r\nContent-Length: 2', 'Content-Length: 2\r\nTransfer-Encoding: chunked', 'Content-Length: +2'):
                with socket.create_connection(server.server_address, timeout=2) as client:
                    header = f'POST /v1/memory HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\nContent-Type: application/json\r\n{framing}\r\n\r\n{{}}'
                    client.sendall(header.encode())
                    self.assertIn(b' 400 ', client.recv(4096).split(b'\r\n')[0])
            self.assertEqual(engine.list_memories('alice'),[])
