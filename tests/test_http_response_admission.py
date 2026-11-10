"""Deterministic synthetic response lifecycle tests; loopback and temporary state."""
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from jace.api import JaceHandler, JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.engine import CognitiveEngine, EngineBusyError

TOKEN = 'synthetic-response-lifecycle-token-' + 'x' * 32

class NeverReason:
    def respond(self,*args,**kwargs): raise AssertionError('No reasoning permitted')

@contextmanager
def fixture(handler, *, release_events=()):
    with tempfile.TemporaryDirectory() as directory:
        engine=CognitiveEngine(Path(directory)/'db',canonical_path='',reasoner=NeverReason())
        server=JaceHTTPServer(('127.0.0.1',0),engine,ApiAuthorization({TOKEN:'synthetic'}))
        server.RequestHandlerClass=handler
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
        try: yield server,engine
        finally:
            for event in release_events:event.set()
            server.shutdown();server.server_close();thread.join(3);engine.close()

def request(server, path='/synthetic', method='GET', body=None):
    conn=http.client.HTTPConnection(*server.server_address,timeout=3)
    try:
        headers={'Authorization':'Bearer '+TOKEN}
        data=None if body is None else json.dumps(body)
        if body is not None:headers['Content-Type']='application/json'
        conn.request(method,path,data,headers);response=conn.getresponse()
        return response.status,json.loads(response.read())
    finally: conn.close()

def get(server):
    return request(server)

class LifecycleTests(unittest.TestCase):
    def test_frozen_snapshot_and_free_engine_at_first_header_and_body_write(self):
        for boundary in ('status','body'):
            with self.subTest(boundary=boundary):
                entered=threading.Event();release=threading.Event();results=[];errors=[]
                payload={'nested':{'value':'before'}}
                def pause():
                    entered.set()
                    if not release.wait(3): raise AssertionError('gate timeout')
                class Handler(JaceHandler):
                    def setup(self):
                        super().setup()
                        if boundary=='body':
                            original=self.wfile
                            class Writer:
                                def write(self,data):
                                    if data.startswith(b'{'):pause()
                                    return original.write(data)
                                def __getattr__(self,name):return getattr(original,name)
                            self.wfile=Writer()
                    def send_response(self,*args,**kwargs):
                        if boundary=='status':pause()
                        return super().send_response(*args,**kwargs)
                    def do_GET(self):
                        self._finish_read();self.engine.list_memories('synthetic')
                        self._send(200,payload)
                with fixture(Handler,release_events=(release,)) as (server,engine):
                    def run():
                        try:results.append(get(server))
                        except Exception as exc:errors.append(repr(exc))
                    worker=threading.Thread(target=run);worker.start()
                    try:
                        self.assertTrue(entered.wait(2))
                        with engine.request_admission():
                            payload['nested']['value']='after'
                            engine.remember('synthetic','I prefer quiet rooms')
                    finally:release.set();worker.join(3)
                    self.assertEqual(errors,[]);self.assertEqual(results,[(200,{'nested':{'value':'before'}})])

    def test_next_stale_request_reaches_revision_check_before_prior_handler_cleanup(self):
        sent=threading.Event();release=threading.Event();finished=threading.Event()
        class Handler(JaceHandler):
            def _send(self,status,payload,**kwargs):
                super()._send(status,payload,**kwargs)
                if self.path=='/v1/memory' and status==409:
                    sent.set()
                    if not release.wait(4):raise AssertionError('post-response gate timeout')
            def handle_one_request(self):
                try:super().handle_one_request()
                finally:
                    if getattr(self,'path',None)=='/v1/memory':finished.set()
        with fixture(Handler,release_events=(release,)) as (server,engine):
            old=engine.remember('synthetic','I prefer quiet rooms')[0]
            current=engine.correct_memory('synthetic',old.memory_id,'I prefer quiet gardens')[0]
            changes=engine.memory.connection.total_changes
            self.assertEqual(request(server,'/v1/memory','PATCH',{
                'memory_id':old.memory_id,'content':'Unused stale change','expected_revision':old.revision})[0],409)
            self.assertTrue(sent.wait(2));self.assertFalse(finished.is_set())
            try:
                self.assertEqual(request(server,'/v1/memory-expiration','PATCH',{
                    'memory_id':old.memory_id,'expires_at':None,'expected_revision':old.revision})[0],409)
                self.assertEqual(engine.list_memories('synthetic'),[current])
                self.assertEqual(engine.memory.connection.total_changes,changes)
            finally:release.set()
            self.assertTrue(finished.wait(2))

    def test_response_serialization_remains_inside_engine_admission(self):
        entered=threading.Event();release=threading.Event();results=[];errors=[]
        payload={'snapshot':'held'};original=json.dumps
        def serialize(value,*args,**kwargs):
            if value is payload:
                entered.set()
                if not release.wait(4):raise AssertionError('serialization gate timeout')
            return original(value,*args,**kwargs)
        class Handler(JaceHandler):
            def do_GET(self):
                self._finish_read();self.engine.list_memories('synthetic');self._send(200,payload)
        with fixture(Handler,release_events=(release,)) as (server,engine):
            def run():
                try:results.append(get(server))
                except Exception as exc:errors.append(repr(exc))
            with patch('jace.api.json.dumps',side_effect=serialize):
                worker=threading.Thread(target=run);worker.start()
                try:
                    self.assertTrue(entered.wait(2))
                    with self.assertRaises(EngineBusyError):
                        with engine.request_admission():pass
                finally:release.set();worker.join(3)
            self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
            self.assertEqual(results,[(200,payload)])

    def test_late_engine_access_and_second_response_are_rejected(self):
        completed=threading.Event();outcomes=[];statuses=[]
        class Handler(JaceHandler):
            def send_response(self,status,*args,**kwargs):
                statuses.append(status);return super().send_response(status,*args,**kwargs)
            def do_GET(self):
                self._finish_read();self.engine.list_memories('synthetic');self._send(200,{'ok':True})
                for operation in (lambda:self.engine.remember('synthetic','I prefer forbidden late writing'),lambda:self._send(200,{'duplicate':True})):
                    try:operation();outcomes.append('allowed')
                    except Exception as exc:outcomes.append(type(exc).__name__)
                completed.set()
        with fixture(Handler) as (server,engine):
            self.assertEqual(get(server),(200,{'ok':True}));self.assertTrue(completed.wait(2))
            self.assertEqual(len(outcomes),2);self.assertNotIn('allowed',outcomes)
            self.assertEqual(statuses,[200])
            self.assertEqual(engine.list_memories('synthetic'),[])

    def test_serialization_failure_can_send_error_then_releases(self):
        class Handler(JaceHandler):
            def do_GET(self):
                self._finish_read();self.engine.list_memories('synthetic')
                try:self._send(200,{'bad':object()})
                except TypeError:self._send(500,{'error':'synthetic serialization failed'})
        with fixture(Handler) as (server,engine):
            self.assertEqual(get(server)[0],500)
            with engine.request_admission():pass

    def test_socket_write_failure_cannot_emit_a_second_response_or_retain_engine(self):
        completed=threading.Event();statuses=[];body_writes=[]
        class Handler(JaceHandler):
            def setup(self):
                super().setup();original=self.wfile
                class Writer:
                    def write(self,data):
                        if data.startswith(b'{'):
                            body_writes.append(data)
                            raise BrokenPipeError('synthetic write failure')
                        return original.write(data)
                    def __getattr__(self,name):return getattr(original,name)
                self.wfile=Writer()
            def send_response(self,status,*args,**kwargs):
                statuses.append(status);return super().send_response(status,*args,**kwargs)
            def do_GET(self):
                self._finish_read();self.engine.list_memories('synthetic')
                try:self._send(200,{'snapshot':True})
                except OSError:self._send(500,{'error':'must not be emitted'})
            def handle_one_request(self):
                try:super().handle_one_request()
                finally:completed.set()
        with fixture(Handler) as (server,engine):
            with self.assertRaises(http.client.IncompleteRead):get(server)
            self.assertTrue(completed.wait(2))
            self.assertEqual(statuses,[200]);self.assertEqual(len(body_writes),1)
            with engine.request_admission():self.assertEqual(engine.list_memories('synthetic'),[])

    def test_failure_before_send_uses_final_cleanup(self):
        complete=threading.Event()
        class Handler(JaceHandler):
            def do_GET(self):
                self._finish_read();self.engine.list_memories('synthetic')
                raise OSError('synthetic early failure')
            def handle_one_request(self):
                try:super().handle_one_request()
                finally:complete.set()
        with fixture(Handler) as (server,engine):
            with self.assertRaises(http.client.RemoteDisconnected):get(server)
            self.assertTrue(complete.wait(2))
            with engine.request_admission():pass

if __name__=='__main__':unittest.main(verbosity=2)
