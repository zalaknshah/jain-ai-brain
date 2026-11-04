import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.memory import MemoryDeletionConsentRequired, MemoryStore
from jace.reasoner import LocalReasoner


class MemoryScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'memory.db'
        self.engine = CognitiveEngine(db_path=self.path, canonical_path='', reasoner=LocalReasoner())

    def tearDown(self):
        self.engine.close(); self.temp.cleanup()

    def remember(self,scope,content='I prefer quiet rooms',user='alice',**kwargs):
        return self.engine.remember(user,content,memory_scope=scope,**kwargs)[0]

    def test_exact_scope_filters_direct_graph_expansion_and_reasoner_context(self):
        default=self.remember('default','I prefer quiet default rooms')
        home=self.remember('home','I prefer quiet home rooms and minimal resources')
        work=self.remember('work','I prefer quiet work rooms and minimal resources')
        bob=self.remember('home','I prefer quiet private rooms',user='bob')
        connection=self.engine.memory.connection
        connection.execute("INSERT INTO graph_edges VALUES (?, ?, 'synthetic_cross_scope', 1)",(f'memory:{home.memory_id}',f'memory:{work.memory_id}'))
        connection.commit()
        captured=[]
        def respond(request,assessment,perspectives,evidence,memories):
            captured.append(memories);return 'A synthetic answer.',None
        with patch.object(self.engine.reasoner,'respond',side_effect=respond):
            for scope,expected in [('default',default),('home',home),('work',work)]:
                result=self.engine.think('alice','quiet minimal resources',memory_scope=scope)
                self.assertEqual(result.memory_scope,scope)
                self.assertEqual(result.to_dict()['memory_scope'],scope)
                self.assertEqual([m.memory_id for m in result.memories_used],[expected.memory_id])
                self.assertEqual([m.memory_id for m in captured[-1]],[expected.memory_id])
                self.assertEqual([m.memory_id for m in self.engine.memory.search('alice','123',memory_scope=scope)],[expected.memory_id])
                hits=self.engine.search_graph('quiet minimal resources','alice',memory_scope=scope)
                self.assertEqual([h.source_id for h in hits if h.node_type=='memory'],[str(expected.memory_id)])
                self.assertTrue(any(h.node_type=='canonical' for h in self.engine.search_graph('Ahimsa','alice',memory_scope=scope)))
            self.assertEqual(self.engine.think('alice','quiet',memory_scope='empty').memories_used,[])
        self.assertEqual(self.engine.list_memories('alice'),[default])
        self.assertEqual(self.engine.list_memories('bob',memory_scope='home'),[bob])

    def test_scope_names_are_owner_bound_and_do_not_include_other_owners(self):
        self.remember('home');self.remember('work');self.remember('private-bob',user='bob')
        self.assertEqual(self.engine.list_memory_scopes('alice'),['default','home','work'])
        self.assertEqual(self.engine.list_memory_scopes('bob'),['default','private-bob'])
        self.assertEqual(self.engine.list_memory_scopes('unknown'),['default'])
        self.assertEqual(self.engine.list_memories('alice',memory_scope='private-bob'),[])

    def test_invalid_scope_never_defaults_or_calls_model_or_writes(self):
        bad=['',None,True,1,[],{},'Home',' home','home ','../home','home/work','a'*65,'हिन्दी','a\n','_home']
        reasoner=Mock();self.engine.reasoner=reasoner
        for scope in bad:
            for call in [lambda:self.engine.remember('alice','I prefer quiet rooms',memory_scope=scope),
                         lambda:self.engine.think('alice','Hello',memory_scope=scope),
                         lambda:self.engine.learn_from_conversation('alice','Hello',memory_scope=scope),
                         lambda:self.engine.list_memories('alice',memory_scope=scope),
                         lambda:self.engine.search_graph('quiet','alice',memory_scope=scope)]:
                with self.subTest(scope=scope),self.assertRaises(ValueError):call()
        reasoner.respond.assert_not_called()
        self.assertEqual(self.engine.memory.list('alice',None),[])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],0)

    def test_correction_expiry_and_single_deletion_preserve_scope_and_other_memories(self):
        home=self.remember('home',expires_at='2000-01-01T00:00:00Z')
        work=self.remember('work')
        corrected,_=self.engine.correct_memory('alice',home.memory_id,'I prefer quiet gardens')
        self.assertEqual(corrected.memory_scope,'home')
        self.assertEqual(self.engine.memory.search('alice','quiet',memory_scope='home'),[])
        renewed=self.engine.set_memory_expiration('alice',home.memory_id,None)
        self.assertEqual(renewed.memory_scope,'home')
        self.assertEqual(self.engine.memory.search('alice','quiet'),[])
        self.assertEqual(self.engine.list_memories('alice',memory_scope='home'),[renewed])
        preview=self.engine.preview_memory_deletion('alice',home.memory_id)
        self.assertEqual(preview['memory']['memory_scope'],'home')
        self.assertEqual(self.engine.forget_memory('alice',home.memory_id,confirm_delete=True),1)
        self.assertEqual(self.engine.list_memories('alice',memory_scope='work'),[work])
        self.assertEqual(self.engine.list_memory_scopes('alice'),['default','work'])

    def test_failed_correction_cannot_change_scope_or_graph(self):
        original=self.remember('home')
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.engine.correct_memory('alice',original.memory_id,'I prefer red rooms')
        self.assertEqual(self.engine.list_memories('alice',memory_scope='home'),[original])
        self.assertEqual(self.engine.list_memories('alice'),[])
        self.assertEqual([h.content for h in self.engine.search_graph('quiet','alice',memory_scope='home') if h.node_type=='memory'],[original.content])

    def test_whole_user_forget_removes_every_scope_and_legacy_warning_is_owner_wide(self):
        home=self.remember('home');work=self.remember('work');bob=self.remember('home',user='bob')
        connection=self.engine.memory.connection
        connection.execute("INSERT INTO memory_audit(user_id,accepted,reason,created_at) VALUES ('alice',0,'legacy','fixture')");connection.commit()
        preview=self.engine.preview_memory_deletion('alice',home.memory_id)
        self.assertIn('across all memory scopes',preview['warning'])
        with self.assertRaises(MemoryDeletionConsentRequired):self.engine.forget_memory('alice',home.memory_id,confirm_delete=True)
        self.assertEqual(self.engine.forget_user('alice'),2)
        self.assertEqual(self.engine.memory.list('alice',None),[])
        self.assertEqual(self.engine.list_memories('bob',memory_scope='home'),[bob])
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_id IN (?,?)",(f'memory:{home.memory_id}',f'memory:{work.memory_id}')).fetchone()[0],0)
        self.assertTrue(self.engine.search_graph('Ahimsa','alice'))

    def test_old_schema_is_migrated_to_default_without_reclassifying_text(self):
        path=Path(self.temp.name)/'old.db'
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE memories(id INTEGER PRIMARY KEY,user_id TEXT,content TEXT,created_at TEXT,source TEXT,updated_at TEXT,expires_at TEXT)')
            connection.execute("INSERT INTO memories VALUES(7,'alice','This text mentions work and home','old','user','updated',NULL)")
        store=MemoryStore(path)
        try:
            record=store.list('alice',memory_scope='default')[0]
            self.assertEqual(record.memory_id,7);self.assertEqual(record.memory_scope,'default')
            self.assertEqual(record.updated_at,'updated')
            self.assertEqual(store.list('alice',memory_scope='work'),[])
            self.assertEqual(store.list('alice',memory_scope='home'),[])
        finally:store.close()
        reopened=MemoryStore(path)
        try:self.assertEqual(reopened.list('alice')[0].memory_scope,'default')
        finally:reopened.close()

    def test_failed_scope_migration_rolls_back_column_and_index(self):
        path=Path(self.temp.name)/'failure.db'
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE memories(id INTEGER PRIMARY KEY,user_id TEXT,content TEXT,created_at TEXT,source TEXT,updated_at TEXT,expires_at TEXT)')
            connection.execute("INSERT INTO memories VALUES(1,'alice','Original','old','user',NULL,NULL)")
        connect=sqlite3.connect;opened=[]
        class Failing(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                if sql.startswith('CREATE INDEX IF NOT EXISTS memories_owner_scope_id'):
                    raise sqlite3.OperationalError('synthetic index failure')
                return super().execute(sql,*args,**kwargs)
        def failing(*args,**kwargs):
            connection=connect(*args,factory=Failing,**kwargs);opened.append(connection);return connection
        try:
            with patch('jace.memory.sqlite3.connect',side_effect=failing),self.assertRaises(sqlite3.OperationalError):MemoryStore(path)
        finally:
            for connection in opened:connection.close()
        with connect(path) as connection:
            self.assertNotIn('memory_scope',[r[1] for r in connection.execute('PRAGMA table_info(memories)')])
            self.assertEqual(connection.execute('SELECT content FROM memories').fetchone()[0],'Original')
        store=MemoryStore(path)
        try:self.assertEqual(store.list('alice')[0].memory_scope,'default')
        finally:store.close()

    def test_two_engines_keep_concurrent_scopes_separate_without_shared_active_state(self):
        other=CognitiveEngine(db_path=self.path,canonical_path='',reasoner=LocalReasoner())
        barrier=threading.Barrier(2);errors=[]
        def save(engine,scope):
            try:
                barrier.wait(timeout=3)
                for index in range(5):engine.remember('alice',f'I prefer quiet {scope} room {index}',memory_scope=scope)
            except Exception as error:errors.append(error)
        a=threading.Thread(target=save,args=(self.engine,'home'));b=threading.Thread(target=save,args=(other,'work'))
        try:
            a.start();b.start();a.join(4);b.join(4)
            self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertEqual(errors,[])
            for engine in [self.engine,other]:
                for scope in ['home','work']:
                    records=engine.list_memories('alice',memory_scope=scope)
                    self.assertEqual(len(records),5);self.assertTrue(all(r.memory_scope==scope for r in records))
                self.assertEqual(engine.list_memories('alice'),[])
        finally:other.close()

    def test_cli_scoped_create_review_and_learning(self):
        env=dict(os.environ,JACE_DB_PATH=str(self.path),JACE_LLM_URL='',JACE_CANONICAL_PATH='',PYTHONPATH='src')
        def cli(*args):return subprocess.run([sys.executable,'-m','jace.cli',*args],env=env,capture_output=True,text=True,timeout=5)
        result=cli('remember','alice','I prefer quiet rooms','--memory-scope','home')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['memory']['memory_scope'],'home')
        self.assertEqual(json.loads(cli('memories','alice').stdout)['memories'],[])
        self.assertEqual(len(json.loads(cli('memories','alice','--memory-scope','home').stdout)['memories']),1)
        result=cli('ask','Remember I prefer quiet work rooms','--user','alice','--memory-scope','work','--learn')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['learned_memory']['memory_scope'],'work')
        self.assertEqual(json.loads(cli('memory-scopes','alice').stdout)['memory_scopes'],['default','home','work'])
        self.assertNotEqual(cli('ask','Hello','--memory-scope','').returncode,0)


class MemoryScopeHTTPTests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request

    def test_scoped_http_learning_and_reads_are_owner_bound(self):
        self.assertEqual(self.request('/health')[1]['memory_scope_protocol'],1)
        status,body,_=self.request('/v1/memory','POST',{'content':'I prefer quiet home rooms','memory_scope':'home'},api_fixture.ALICE_TOKEN)
        self.assertEqual(status,201);mid=body['memory']['memory_id']
        status,body,_=self.request('/v1/think','POST',{'input':'Remember I prefer quiet work rooms','memory_scope':'work','learn':True},api_fixture.ALICE_TOKEN)
        self.assertEqual(status,200);self.assertEqual(body['memory_scope'],'work');self.assertEqual(body['learned_memory']['memory_scope'],'work')
        self.assertEqual(body['memories_used'],[])
        self.assertEqual(len(self.request('/v1/memory/alice',token=api_fixture.ALICE_TOKEN)[1]['memories']),1)
        home=self.request('/v1/memory/alice?memory_scope=home',token=api_fixture.ALICE_TOKEN)[1]
        self.assertEqual(home['memory_scope'],'home');self.assertEqual([m['memory_id'] for m in home['memories']],[mid])
        hits=self.request('/v1/graph/search?q=quiet&memory_scope=home',token=api_fixture.ALICE_TOKEN)[1]['hits']
        self.assertEqual([h['source_id'] for h in hits if h['node_type']=='memory'],[str(mid)])
        self.assertEqual(self.request('/v1/memory-scopes',token=api_fixture.ALICE_TOKEN)[1]['memory_scopes'],['default','home','work'])
        self.assertEqual(self.request('/v1/memory-scopes',token=api_fixture.BOB_TOKEN)[1]['memory_scopes'],['default'])
        self.assertEqual(self.request('/v1/memory/alice?memory_scope=home',token=api_fixture.BOB_TOKEN)[0],403)
        self.assertEqual(self.request('/v1/memory-scopes')[0],401)
        self.assertEqual(self.request('/v1/memory-item/'+str(mid),token=api_fixture.BOB_TOKEN)[0],404)

    def test_invalid_ambiguous_or_misspelled_scopes_do_not_fall_back(self):
        for value in ['',None,True,'Home','../home']:
            for path,body in [('/v1/memory',{'content':'I prefer red','memory_scope':value}),('/v1/think',{'input':'Hello','memory_scope':value})]:
                self.assertEqual(self.request(path,'POST',body,api_fixture.ALICE_TOKEN)[0],400)
        for path in ['/v1/memory/alice?memory_scope=', '/v1/memory/alice?memory_scope=home&memory_scope=work',
                     '/v1/memory/alice?scope=home','/v1/memory/alice;anything?memory_scope=home',
                     '/v1/graph/search?q=quiet&memory_scope=', '/v1/graph/search?q=quiet&scope=home',
                     '/v1/memory-scopes?user_id=bob']:
            self.assertEqual(self.request(path,token=api_fixture.ALICE_TOKEN)[0],400,path)
        self.assertEqual(len(self.engine.memory.list('alice',None)),1)

    def test_misspelled_post_selectors_and_unknown_patch_fields_fail_closed(self):
        original = self.engine.list_memories('alice')[0]
        with patch.object(self.engine, 'think') as think:
            for key in ['scope', 'memoryScope', 'memory_scopes', 'memroy_scope']:
                self.assertEqual(self.request('/v1/memory', 'POST', {'content':'I prefer private project plans', key:'project'}, api_fixture.ALICE_TOKEN)[0], 400)
                self.assertEqual(self.request('/v1/think', 'POST', {'input':'private project plans', key:'project'}, api_fixture.ALICE_TOKEN)[0], 400)
            self.assertEqual(self.request('/v1/think', 'POST', {'input':'Remember private plans', 'learn':'true'}, api_fixture.ALICE_TOKEN)[0], 400)
            think.assert_not_called()
        self.assertEqual(self.request('/v1/memory', 'PATCH', {'memory_id':original.memory_id, 'content':'Changed', 'scope':'work'}, api_fixture.ALICE_TOKEN)[0], 400)
        self.assertEqual(self.request('/v1/memory-expiration', 'PATCH', {'memory_id':original.memory_id, 'expires_at':None, 'scope':'work'}, api_fixture.ALICE_TOKEN)[0], 400)
        self.assertEqual(self.engine.list_memories('alice'), [original])
        self.assertEqual(self.engine.list_memory_scopes('alice'), ['default'])

    def test_scope_cannot_be_silently_changed_by_correction_or_duplicate_json(self):
        original=self.engine.list_memories('alice')[0]
        for path,body in [('/v1/memory',{'memory_id':original.memory_id,'content':'Changed','memory_scope':'work'}),
                          ('/v1/memory-expiration',{'memory_id':original.memory_id,'expires_at':None,'memory_scope':'work'})]:
            self.assertEqual(self.request(path,'PATCH',body,api_fixture.ALICE_TOKEN)[0],400)
        raw=b'{"content":"I prefer red","memory_scope":"home","memory_scope":"work"}'
        request=Request(f'http://127.0.0.1:{self.server.server_port}/v1/memory',data=raw,method='POST',
                        headers={'Content-Type':'application/json','Authorization':'Bearer '+api_fixture.ALICE_TOKEN})
        with self.assertRaises(HTTPError) as raised:urlopen(request,timeout=2)
        self.assertEqual(raised.exception.code,400);raised.exception.close()
        self.assertEqual(self.engine.list_memories('alice'),[original])


if __name__=='__main__':unittest.main()
