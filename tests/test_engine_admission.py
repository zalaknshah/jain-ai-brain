"""Synthetic loopback tests for nonqueued, request-scoped engine work."""
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jace.api import JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.engine import CognitiveEngine, EngineBusyError
from jace.reasoner import LocalReasoner

TOKEN = 'synthetic-admission-token-' + 'x' * 32


class GatedReasoner(LocalReasoner):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def respond(self, *args):
        self.calls += 1
        self.started.set()
        if not self.release.wait(8):
            raise RuntimeError('synthetic test gate was not released')
        return super().respond(*args)


@contextmanager
def service(reasoner=None):
    with tempfile.TemporaryDirectory() as directory:
        engine = CognitiveEngine(db_path=Path(directory)/'db', reasoner=reasoner or LocalReasoner())
        server = JaceHTTPServer(('127.0.0.1',0), engine, ApiAuthorization({TOKEN:'alice'}),
                                rate_burst=100, rate_per_minute=600, request_timeout=1)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.01})
        thread.start()
        try:
            yield server,engine
        finally:
            if isinstance(reasoner,GatedReasoner):
                reasoner.release.set()
            server.shutdown();server.server_close();thread.join(3);engine.close()


def call(server,path='/health',method='GET',body=None,headers=None,raw=None):
    fields={'Authorization':'Bearer '+TOKEN}
    if body is not None or raw is not None:
        fields['Content-Type']='application/json'
    fields.update(headers or {})
    data=json.dumps(body).encode() if body is not None else raw
    req=Request(f'http://127.0.0.1:{server.server_port}{path}',data=data,method=method,headers=fields)
    try:
        response=urlopen(req,timeout=4)
    except HTTPError as error:
        response=error
    with response:
        wire=response.read()
        return response.status,json.loads(wire) if wire else None,response.headers


def begin_thought(server,reasoner,*,learn=False):
    result=[]
    def run():
        try:
            result.append(call(server,'/v1/think','POST',{'input':'I prefer quiet rooms','learn':learn}))
        except Exception as error:
            result.append(error)
    thread=threading.Thread(target=run);thread.start()
    if not reasoner.started.wait(3):
        reasoner.release.set();thread.join(3)
        raise AssertionError('synthetic reasoner did not start')
    return thread,result


class EngineAdmissionTests(unittest.TestCase):
    def assert_busy(self,response):
        status,body,headers=response
        self.assertEqual(status,503)
        self.assertEqual(body['code'],'engine_busy')
        self.assertIs(body['request_started'],False)
        self.assertIs(body['automatic_retry'],False)
        self.assertNotIn('Retry-After',headers)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn(TOKEN,json.dumps(body))

    def test_all_engine_routes_reject_without_queueing_writes(self):
        reasoner=GatedReasoner()
        with service(reasoner) as (server,engine):
            memory,_=engine.remember('alice','I prefer gentle cleaning')
            thread,result=begin_thought(server,reasoner,learn=True)
            routes=[
                ('GET',f'/v1/memory-item/{memory.memory_id}',None,{}),
                ('GET','/v1/canonical/search?q=care',None,{}),
                ('GET','/v1/memory-scopes',None,{}),
                ('GET','/v1/graph/search?q=care',None,{}),
                ('GET','/v1/memory/alice',None,{}),
                ('DELETE',f'/v1/memory-item/{memory.memory_id}',None,{'X-JACE-Confirm-Delete':str(memory.memory_id)}),
                ('DELETE','/v1/memory/alice',None,{'X-JACE-Confirm-Owner-Delete':'all-memories-graph-and-audit:alice'}),
                ('PATCH','/v1/memory',{'memory_id':memory.memory_id,'content':'I prefer unwanted changes'},{}),
                ('PATCH','/v1/memory-expiration',{'memory_id':memory.memory_id,'expires_at':None},{}),
                ('PATCH','/v1/cleaning-profiles',{'memory_id':memory.memory_id,'profile':{}},{}),
                ('PATCH','/v1/wardrobe-inventories',{'memory_id':memory.memory_id,'inventory':{}},{}),
                ('POST','/v1/context/preview',{'input':'Hello'},{}),
                ('POST','/v1/context/answer',{'input':'Hello'},{}),
                ('POST','/v1/wardrobe-inventories',{'inventory':{}},{}),
                ('POST','/v1/plans/wardrobe',{},{}),
                ('POST','/v1/cleaning-profiles',{'profile':{}},{}),
                ('POST','/v1/plans/cleaning',{},{}),
                ('POST','/v1/think',{'input':'I prefer rejected learning','learn':True},{}),
                ('POST','/v1/memory',{'content':'I prefer rejected writing'},{}),
            ]
            try:
                started=time.monotonic()
                for method,path,body,headers in routes:
                    with self.subTest(method=method,path=path):
                        self.assert_busy(call(server,path,method,body,headers))
                self.assertLess(time.monotonic()-started,3)
                self.assertEqual(reasoner.calls,1)
            finally:
                reasoner.release.set();thread.join(4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result[0][0],200)
            contents=[memory.content for memory in engine.list_memories('alice')]
            self.assertEqual(len(contents),2)
            self.assertIn('I prefer gentle cleaning',contents)
            self.assertIn('I prefer quiet rooms',contents)
            self.assertFalse(any('rejected' in value or 'unwanted' in value for value in contents))
            self.assertEqual(reasoner.calls,1)
            self.assertEqual(call(server,'/v1/memory','POST',{'content':'I prefer a fresh request'})[0],201)

    def test_health_auth_validation_and_stateless_routes_do_not_wait_for_engine(self):
        reasoner=GatedReasoner()
        with service(reasoner) as (server,_):
            thread,result=begin_thought(server,reasoner)
            try:
                self.assertEqual(call(server)[0],200)
                busy=call(server,'/v1/memory/alice',headers={'Origin':'http://127.0.0.1:8080'})
                self.assert_busy(busy)
                self.assertEqual(busy[2]['Access-Control-Allow-Origin'],'http://127.0.0.1:8080')
                self.assertEqual(call(server,'/missing')[0],404)
                self.assertEqual(call(server,'/missing','POST',{})[0],404)
                self.assertEqual(call(server,'/v1/memory/alice',headers={'Authorization':''})[0],401)
                self.assertEqual(call(server,'/v1/memory/bob')[0],403)
                self.assertEqual(call(server,'/v1/memory','POST',{'user_id':'bob','content':'no'})[0],403)
                self.assertEqual(call(server,'/v1/memory','POST',raw=b'{')[0],400)
                self.assertEqual(call(server,'/v1/memory','POST',{},headers={'Content-Type':'text/plain'})[0],400)
                self.assertEqual(call(server,'/v1/memory/alice',headers={'Origin':'https://unapproved.example'})[0],403)
                self.assertEqual(call(server,'/v1/memory','OPTIONS',headers={'Origin':'http://127.0.0.1:8080'})[0],204)
                self.assertEqual(call(server,'/v1/simulate/motion','POST',{'observation':{}})[0],200)
            finally:
                reasoner.release.set();thread.join(4)
            self.assertEqual(result[0][0],200)

    def test_incomplete_authenticated_body_does_not_reserve_engine(self):
        with service() as (server,engine):
            with socket.create_connection(server.server_address,timeout=3) as client:
                header=(f'POST /v1/memory HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\n'
                        'Content-Type: application/json\r\nContent-Length: 100\r\n\r\n').encode()
                client.sendall(header+b'{"content":"')
                self.assertEqual(call(server,'/v1/memory/alice')[0],200)
                self.assertEqual(call(server,'/v1/memory','POST',{'content':'I prefer completed requests'})[0],201)
                client.shutdown(socket.SHUT_WR)
                client.recv(4096)
            self.assertEqual([memory.content for memory in engine.list_memories('alice')],['I prefer completed requests'])

    def test_admission_spans_think_and_optional_learning(self):
        with service() as (server,engine):
            entered=threading.Event();release=threading.Event();original=engine.learn_from_conversation
            def learn(*args,**kwargs):
                entered.set()
                if not release.wait(5):raise RuntimeError('synthetic learning gate timed out')
                return original(*args,**kwargs)
            result=[]
            with patch.object(engine,'learn_from_conversation',side_effect=learn):
                thread=threading.Thread(target=lambda:result.append(call(server,'/v1/think','POST',{
                    'input':'I prefer quiet rooms','learn':True})))
                thread.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assert_busy(call(server,'/v1/memory/alice'))
                    self.assert_busy(call(server,'/v1/memory','POST',{'content':'I prefer rejected writes'}))
                finally:
                    release.set();thread.join(4)
            self.assertEqual(result[0][0],200)
            self.assertEqual([memory.content for memory in engine.list_memories('alice')],['I prefer quiet rooms'])

    def test_engine_context_reentrant_and_released_after_error(self):
        with service() as (_,engine):
            with engine.request_admission():
                with engine.request_admission():
                    self.assertEqual(engine.list_memories('alice'),[])
            with self.assertRaisesRegex(RuntimeError,'fixture'):
                with engine.request_admission():
                    raise RuntimeError('fixture')
            errors=[]
            def acquire():
                try:
                    with engine.request_admission():pass
                except Exception as error:errors.append(error)
            thread=threading.Thread(target=acquire);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_direct_engine_work_uses_same_lock_but_keeps_blocking_semantics(self):
        reasoner=GatedReasoner()
        with service(reasoner) as (server,engine):
            first=threading.Thread(target=lambda:engine.think('alice','Hello'))
            first.start();self.assertTrue(reasoner.started.wait(3))
            completed=threading.Event()
            second=threading.Thread(target=lambda:(engine.list_memories('alice'),completed.set()))
            second.start()
            try:
                with self.assertRaises(EngineBusyError):
                    with engine.request_admission():pass
                self.assert_busy(call(server,'/v1/memory/alice'))
                self.assertFalse(completed.wait(.05))
            finally:
                reasoner.release.set();first.join(4);second.join(4)
            self.assertTrue(completed.is_set())

    def test_validation_and_unexpected_failures_release_admission(self):
        with service() as (server,engine):
            for failure,status in ((ValueError('synthetic invalid choice'),400),(RuntimeError('synthetic private failure'),500)):
                with patch.object(engine,'remember',side_effect=failure):
                    result=call(server,'/v1/memory','POST',{'content':'I prefer quiet rooms'})
                    self.assertEqual(result[0],status)
                    if status==500:self.assertNotIn('private',json.dumps(result[1]))
                self.assertEqual(call(server,'/v1/memory/alice')[0],200)
            self.assertEqual(call(server,'/v1/memory','POST',{'content':'I prefer quiet rooms'})[0],201)

    def test_client_disconnect_does_not_leak_admission_or_cancel_accepted_work(self):
        reasoner=GatedReasoner()
        with service(reasoner) as (server,engine):
            raw=json.dumps({'input':'I prefer quiet rooms','learn':True}).encode()
            client=socket.create_connection(server.server_address,timeout=3)
            header=(f'POST /v1/think HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {TOKEN}\r\n'
                    f'Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n\r\n').encode()
            client.sendall(header+raw)
            self.assertTrue(reasoner.started.wait(3))
            client.close();reasoner.release.set()
            deadline=time.monotonic()+3
            while True:
                response=call(server,'/v1/memory/alice')
                if response[0]!=503 or time.monotonic()>deadline:break
                time.sleep(.01)
            self.assertEqual(response[0],200)
            self.assertEqual([memory.content for memory in engine.list_memories('alice')],['I prefer quiet rooms'])
            self.assertEqual(reasoner.calls,1)


if __name__=='__main__':unittest.main()
