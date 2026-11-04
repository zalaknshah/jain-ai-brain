"""Offline subprocess and loopback fixtures, never a real model provider."""
import base64
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from jace.engine import CognitiveEngine
from jace.ethics import assess
from jace.model_transport import BoundedModelOpener, ModelTransportError, _worker_environment
from jace.model_transport_worker import (MAX_JOB_BYTES, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
                                         bounded_timeout, validate_job)
from jace.reasoner import HttpJsonReasoner

TOKEN = 'synthetic-transport-token-not-real'
ANSWER = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant',
    'content': json.dumps({'answer': 'Synthetic answer.', 'citations': []})}}]}).encode()


def request(payload=b'{}', url='http://127.0.0.1:1/test', token=TOKEN):
    return urllib.request.Request(url, data=payload, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Accept-Encoding': 'identity', 'Authorization': 'Bearer ' + token})


def job(**changes):
    value = {'url': 'http://127.0.0.1:1/test', 'api_key': TOKEN,
             'payload_base64': base64.b64encode(b'{}').decode(), 'timeout_seconds': 1}
    value.update(changes)
    return json.dumps(value).encode()


@contextmanager
def fixture(mode='valid'):
    seen = []
    disconnected = threading.Event()
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            seen.append((self.path, self.headers.get('Authorization'), body))
            try:
                if mode == 'no_headers':
                    stop.wait(3)
                    return
                if mode == 'slow_headers':
                    for byte in b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n':
                        self.connection.sendall(bytes([byte]))
                        if stop.wait(.04):
                            return
                    return
                if mode == 'redirect':
                    self.send_response(307)
                    self.send_header('Location', '/must-not-follow')
                    self.end_headers()
                    return
                self.send_response(200 if mode != 'bad_status' else 503)
                if mode in ('encoding', 'duplicate_encoding'):
                    self.send_header('Content-Encoding', 'identity' if mode == 'duplicate_encoding' else 'gzip')
                if mode == 'duplicate_encoding':
                    self.send_header('Content-Encoding', 'gzip')
                data = b'x' * (MAX_RESPONSE_BYTES + 1) if mode == 'oversize' else ANSWER
                if mode == 'truncated':
                    data = data[:-3]
                declared = len(data) + 50 if mode == 'truncated_framing' else len(data)
                if mode == 'invalid_length':
                    declared = 'not-a-length'
                if mode not in ('chunked', 'chunked_truncated'):
                    self.send_header('Content-Length', str(declared))
                if mode == 'duplicate_length':
                    self.send_header('Content-Length', str(len(data)))
                if mode in ('mixed_framing', 'chunked', 'chunked_truncated'):
                    self.send_header('Transfer-Encoding', 'chunked')
                if mode == 'unsupported_transfer':
                    self.send_header('Transfer-Encoding', 'gzip')
                self.end_headers()
                if mode in ('chunked', 'chunked_truncated'):
                    self.wfile.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
                    if mode == 'chunked':
                        self.wfile.write(b'0\r\n\r\n')
                    self.wfile.flush()
                    return
                if mode == 'slow_body':
                    for byte in data:
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        if stop.wait(.04):
                            return
                else:
                    self.wfile.write(data)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                disconnected.set()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/test', seen, disconnected
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


class TransportEnvelopeTests(unittest.TestCase):
    def test_exact_body_round_trip_and_job_bounds(self):
        body = ('{"synthetic":"' + 'અ' * 300 + '"}').encode()
        result = validate_job(job(payload_base64=base64.b64encode(body).decode()))
        self.assertEqual(result['payload'], body)
        limit = b'x' * MAX_REQUEST_BYTES
        self.assertEqual(validate_job(job(payload_base64=base64.b64encode(limit).decode()))['payload'], limit)
        with self.assertRaises(ValueError):
            validate_job(job(payload_base64=base64.b64encode(limit + b'x').decode()))

    def test_invalid_schema_duplicates_and_encoding(self):
        malformed = [b'', b'null', b'[]', b'{', b'x' * (MAX_JOB_BYTES + 1),
            job(extra='not allowed'), job(payload_base64='bad!'), job(payload_base64=''),
            job(payload_base64=12), job(payload_base64='અ'),
            job(payload_base64=base64.b64encode(b'\xff').decode()),
            job()[:-1] + b',"api_key":"duplicate"}',
            job().replace(b'"timeout_seconds": 1', b'"timeout_seconds": NaN')]
        for raw in malformed:
            with self.subTest(raw=raw[:50]), self.assertRaises((ValueError, TypeError)):
                validate_job(raw)

    def test_timeout_validation_rejects_unbounded_and_boolean_values(self):
        for value in (0, -1, 31, True, None, '1', float('nan'), float('inf'), 10**10000):
            with self.subTest(type=type(value)), self.assertRaises(ValueError):
                bounded_timeout(value)
        self.assertEqual(bounded_timeout(.125), .125)
        self.assertEqual(bounded_timeout(30), 30.)

    def test_invalid_destination_and_secret_rejected_before_spawn(self):
        for changes in ({'url':'http://example.com'}, {'url':'http://localhost:1'},
                        {'url':'https://user:secret@example.com'}, {'url':'https://example.com/#fragment'},
                        {'api_key':'synthetic\r\nInjected: true'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_job(job(**changes))
        with patch('jace.model_transport.subprocess.run') as run:
            for req in (request(payload=b''), request(payload=b'x' * (MAX_REQUEST_BYTES + 1)),
                        request(url='http://example.com'), urllib.request.Request('https://example.com')):
                with self.assertRaises(ValueError):
                    BoundedModelOpener().open(req)
            run.assert_not_called()

    def test_unexpected_headers_and_invalid_timeout_rejected_before_spawn(self):
        with patch('jace.model_transport.subprocess.run') as run:
            for name, value in (('Proxy-Authorization','secret'), ('X-Extra','secret'),
                                ('Accept','text/plain'), ('Authorization','Basic secret')):
                req = request(); req.add_header(name,value)
                with self.assertRaises(ValueError):
                    BoundedModelOpener().open(req)
            with self.assertRaises(ValueError):
                BoundedModelOpener().open(request(), timeout=31)
            run.assert_not_called()

    def test_launch_isolated_no_credentials_in_argv_env_or_files(self):
        private_env = {name:'synthetic-environment-secret' for name in (
            'HTTP_PROXY','HTTPS_PROXY','SSL_CERT_FILE','JACE_LLM_API_KEY','HF_TOKEN',
            'PYTHONPATH','PYTHONSTARTUP','LD_PRELOAD','PATH')}
        with patch.dict(os.environ, private_env), patch('jace.model_transport.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, ANSWER)
            with BoundedModelOpener().open(request(), timeout=.5) as response:
                self.assertEqual(response.read(), ANSWER)
            args, options = run.call_args
            self.assertTrue(Path(args[0][0]).is_absolute())
            self.assertEqual(args[0][1:3], ['-I','-S'])
            self.assertTrue(Path(args[0][3]).is_absolute())
            self.assertEqual(Path(args[0][3]).name,'model_transport_worker.py')
            self.assertNotIn(TOKEN, repr(args))
            self.assertEqual(set(options['env']) - {'SYSTEMROOT','WINDIR'}, set())
            self.assertNotIn(TOKEN, repr(options['env']))
            self.assertNotIn('synthetic-environment-secret', repr(options['env']))
            self.assertIs(options['stderr'], subprocess.DEVNULL)
            self.assertIs(options['shell'], False)
            self.assertIs(options['close_fds'], True)
            self.assertEqual(options['timeout'], .5)
            self.assertEqual(validate_job(options['input'])['api_key'],TOKEN)

    def test_spawn_failure_and_timeout_never_retry_or_echo(self):
        for error in (OSError('private synthetic error'), subprocess.TimeoutExpired('secret command',.1,output=b'private output')):
            with self.subTest(error=type(error)), patch('jace.model_transport.subprocess.run',side_effect=error) as run:
                with self.assertRaises(ModelTransportError) as caught:
                    BoundedModelOpener().open(request())
                self.assertNotIn('private',str(caught.exception))
                self.assertNotIn('secret',str(caught.exception))
                self.assertIn('No automatic retry', str(caught.exception))
                run.assert_called_once()

    def test_bad_worker_result_rejected_without_partial_output(self):
        for code, body in ((2,b'private response'),(0,None),(0,'not bytes'),(0,b'x'*(MAX_RESPONSE_BYTES+1))):
            with self.subTest(code=code,body_type=type(body)), patch('jace.model_transport.subprocess.run',
                    return_value=subprocess.CompletedProcess([],code,body)):
                with self.assertRaises(ModelTransportError):
                    BoundedModelOpener().open(request())

    def test_worker_rejects_malformed_input_without_stdout_or_stderr(self):
        worker = Path(__file__).resolve().parents[1]/'src/jace/model_transport_worker.py'
        for raw in (b'{"api_key":"synthetic-private"}', job(timeout_seconds=False)):
            result = subprocess.run([sys.executable,'-I','-S',str(worker)],input=raw,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3,env=_worker_environment())
            self.assertEqual(result.returncode,2)
            self.assertEqual((result.stdout,result.stderr),(b'',b''))


class TransportLoopbackTests(unittest.TestCase):
    def test_valid_response_reaches_only_configured_target_ignoring_proxy(self):
        with fixture() as (url,seen,_), patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:1',
                'HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            answer,_=HttpJsonReasoner(url,api_key=TOKEN).respond('Hello',assess('Hello'),[],[],[])
            self.assertIn('Generated answer',answer)
            self.assertIn('Synthetic answer.',answer)
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0][1],'Bearer '+TOKEN)
            self.assertNotIn(TOKEN,answer)

    def test_failed_responses_and_redirect_never_retried(self):
        for mode in ('bad_status','oversize','encoding','duplicate_encoding','truncated','redirect',
                     'truncated_framing','invalid_length','duplicate_length','mixed_framing',
                     'unsupported_transfer','chunked_truncated'):
            with self.subTest(mode=mode), fixture(mode) as (url,seen,_):
                answer,_=HttpJsonReasoner(url,api_key=TOKEN).respond('Hello',assess('Hello'),[],[],[])
                self.assertIn('local rule-based response',answer)
                self.assertNotIn(TOKEN,answer)
                self.assertNotIn('Synthetic answer.',answer)
                self.assertEqual(len(seen),1)
                self.assertEqual(seen[0][0],'/test')

    def test_complete_chunked_response_accepted(self):
        with fixture('chunked') as (url,seen,_):
            answer,_=HttpJsonReasoner(url).respond('Hello',assess('Hello'),[],[],[])
            self.assertIn('Synthetic answer.',answer)
            self.assertEqual(len(seen),1)

    def test_slow_headers_and_body_bounded_with_child_reaped(self):
        real_popen=subprocess.Popen
        for mode in ('no_headers','slow_headers','slow_body'):
            children=[]
            def start(*args,**kwargs):
                child=real_popen(*args,**kwargs);children.append(child);return child
            with self.subTest(mode=mode), fixture(mode) as (url,seen,_), patch('jace.model_transport.subprocess.Popen',side_effect=start):
                adapter=HttpJsonReasoner(url,api_key=TOKEN);adapter.IO_TIMEOUT_SECONDS=1.5
                begin=time.monotonic()
                answer,_=adapter.respond('Hello',assess('Hello'),[],[],[])
                elapsed=time.monotonic()-begin
                self.assertIn('local rule-based response',answer)
                self.assertNotIn('Synthetic answer.',answer)
                self.assertNotIn(TOKEN,answer)
                self.assertGreater(elapsed,1.2)
                self.assertLess(elapsed,4)  # Scheduling tolerance, not a real-time guarantee.
                self.assertEqual(len(seen),1)
                self.assertEqual(len(children),1)
                self.assertIsNotNone(children[0].poll())
                self.assertIsNotNone(children[0].returncode)

    def test_python_startup_hooks_do_not_run_in_worker(self):
        with tempfile.TemporaryDirectory() as directory, fixture() as (url,seen,_):
            directory=Path(directory);marker=directory/'hook-ran.txt'
            (directory/'sitecustomize.py').write_text(f'open({str(marker)!r},"w").write("unexpected")')
            with patch.dict(os.environ,{'PYTHONPATH':str(directory),'PYTHONSTARTUP':str(directory/'sitecustomize.py')}):
                answer,_=HttpJsonReasoner(url).respond('Hello',assess('Hello'),[],[],[])
            self.assertIn('Generated answer',answer)
            self.assertFalse(marker.exists())
            self.assertEqual(len(seen),1)

    def test_engine_lock_released_after_timed_out_attempt(self):
        with tempfile.TemporaryDirectory() as directory, fixture('slow_body') as (url,seen,_):
            adapter=HttpJsonReasoner(url);adapter.IO_TIMEOUT_SECONDS=1.5
            engine=CognitiveEngine(db_path=Path(directory)/'memory.db',reasoner=adapter)
            try:
                result=[]
                thread=threading.Thread(target=lambda:result.append(engine.think('synthetic','Hello')))
                thread.start();thread.join(4)
                self.assertFalse(thread.is_alive())
                self.assertIn('local rule-based response',result[0].response)
                self.assertEqual(engine.list_memories('synthetic'),[])
                self.assertEqual(len(seen),1)
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
