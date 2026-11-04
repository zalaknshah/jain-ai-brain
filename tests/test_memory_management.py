import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api_authorization as api_fixture
from jace.engine import CognitiveEngine
from jace.memory import MemoryConflictError
from jace.reasoner import LocalReasoner


class MemoryManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'db'
        self.engine=CognitiveEngine(self.db,canonical_path='',reasoner=LocalReasoner())
        self.memory=self.engine.remember('alice','I prefer quiet rooms')[0]

    def tearDown(self):
        self.engine.close();self.temp.cleanup()

    def test_page_is_owner_scope_bound_and_reaches_older_records(self):
        self.engine.remember('bob','Private Bob memory')
        self.engine.remember('alice','Work scope memory',memory_scope='work')
        expected=[self.memory.memory_id]
        for n in range(45):expected.append(self.engine.remember('alice',f'Original fixture {n}')[0].memory_id)
        before=None;seen=[]
        while True:
            page=self.engine.memory_page('alice',limit=7,before_id=before)
            self.assertTrue(all(m['user_id']=='alice' and m['memory_scope']=='default' for m in page['memories']))
            self.assertTrue(all(len(m['revision'])==64 for m in page['memories']))
            seen.extend(m['memory_id'] for m in page['memories'])
            before=page['next_before_id']
            if before is None:break
        self.assertEqual(seen,list(reversed(expected)))
        self.assertEqual(self.engine.memory_page('nobody')['memories'],[])
        for bad in (0,True,-1,2**63,'1'):
            with self.assertRaises(ValueError):self.engine.memory_page('alice',before_id=bad)

    def test_cursor_is_keyset_not_offset_with_insertions_and_deletions(self):
        for n in range(6):self.engine.remember('alice',f'Fixture {n}')
        first=self.engine.memory_page('alice',limit=3)
        self.engine.remember('alice','Newest fixture')
        self.engine.forget_memory('alice',first['memories'][0]['memory_id'],confirm_delete=True)
        second=self.engine.memory_page('alice',limit=3,before_id=first['next_before_id'])
        self.assertTrue(all(m['memory_id']<first['next_before_id'] for m in second['memories']))
        self.assertEqual(set(m['memory_id'] for m in first['memories']) & set(m['memory_id'] for m in second['memories']),set())

    def test_revision_conflicts_precede_all_three_mutations_and_audit(self):
        old=self.memory.revision
        current=self.engine.correct_memory('alice',self.memory.memory_id,'I prefer bright rooms',expected_revision=old)[0]
        self.assertNotEqual(old,current.revision)
        before=self.engine.memory.connection.total_changes
        for call in (lambda:self.engine.correct_memory('alice',current.memory_id,'Wrong',expected_revision=old),
                     lambda:self.engine.set_memory_expiration('alice',current.memory_id,None,expected_revision=old),
                     lambda:self.engine.forget_memory('alice',current.memory_id,confirm_delete=True,expected_revision=old)):
            with self.assertRaises(MemoryConflictError):call()
        self.assertEqual(self.engine.memory.connection.total_changes,before)
        self.assertEqual(self.engine.list_memories('alice'),[current])
        updated=self.engine.set_memory_expiration('alice',current.memory_id,'2000-01-01T00:00:00Z',expected_revision=current.revision)
        self.assertNotEqual(updated.revision,current.revision)
        self.assertEqual(self.engine.forget_memory('alice',current.memory_id,confirm_delete=True,expected_revision=updated.revision),1)

    def test_revision_preserves_owner_check_and_requires_exact_format(self):
        for revision in ('',True,1,'a'*63,'A'*64,'a'*64+'\n'):
            with self.assertRaises(ValueError):self.engine.correct_memory('alice',self.memory.memory_id,'Replacement',expected_revision=revision)
        with self.assertRaises(LookupError):self.engine.correct_memory('bob',self.memory.memory_id,'Replacement',expected_revision=self.memory.revision)
        with self.assertRaises(ValueError):self.engine.correct_memory('alice',2**63,'Replacement')
        self.assertEqual(self.engine.list_memories('alice'),[self.memory])

    def test_revision_and_content_rollback_after_graph_failure(self):
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):self.engine.correct_memory('alice',self.memory.memory_id,'New fixture',expected_revision=self.memory.revision)
        current=self.engine.memory.get_owned('alice',self.memory.memory_id)
        self.assertEqual(current.revision,self.memory.revision)
        self.assertEqual(current,self.memory)

    def test_two_engines_with_same_review_allow_only_one_mutation(self):
        other=CognitiveEngine(self.db,canonical_path='',reasoner=LocalReasoner())
        barrier=threading.Barrier(2);outcomes=[]
        def change(engine,text):
            barrier.wait()
            try:engine.correct_memory('alice',self.memory.memory_id,text,expected_revision=self.memory.revision);outcomes.append('updated')
            except MemoryConflictError:outcomes.append('conflict')
        try:
            threads=[threading.Thread(target=change,args=(self.engine,'First fixture')),threading.Thread(target=change,args=(other,'Second fixture'))]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=3);self.assertFalse(thread.is_alive())
            self.assertEqual(sorted(outcomes),['conflict','updated'])
        finally:other.close()


class MemoryManagementApiTests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request

    def test_page_revision_health_and_cors(self):
        self.assertEqual(self.request('/health')[1]['memory_management_protocol'],1)
        status,page,_=self.request('/v1/memory/alice?limit=1',token=api_fixture.ALICE_TOKEN)
        self.assertEqual(status,200);self.assertIn('revision',page['memories'][0])
        for query in ('limit=0','limit=01','limit=101','before_id=0','before_id=9223372036854775808','before_id=1&before_id=2','offset=0'):
            self.assertEqual(self.request('/v1/memory/alice?'+query,token=api_fixture.ALICE_TOKEN)[0],400,query)
        self.assertEqual(self.request('/v1/memory/alice?limit=1',token=api_fixture.BOB_TOKEN)[0],403)
        status,_,headers=self.request('/v1/memory','OPTIONS',headers={'Origin':'http://127.0.0.1:8080'})
        self.assertEqual(status,204);self.assertIn('X-JACE-If-Memory-Revision',headers['Access-Control-Allow-Headers'])

    def test_stale_http_mutations_return_conflict_and_require_revision_format(self):
        memory=self.engine.list_memories('alice')[0]
        changed=self.engine.correct_memory('alice',memory.memory_id,'I prefer quiet gardens')[0]
        body={'memory_id':memory.memory_id,'content':'Replace me','expected_revision':memory.revision}
        self.assertEqual(self.request('/v1/memory','PATCH',body,api_fixture.ALICE_TOKEN)[0],409)
        body={'memory_id':memory.memory_id,'expires_at':None,'expected_revision':memory.revision}
        self.assertEqual(self.request('/v1/memory-expiration','PATCH',body,api_fixture.ALICE_TOKEN)[0],409)
        headers={'X-JACE-Confirm-Delete':str(memory.memory_id),'X-JACE-If-Memory-Revision':memory.revision}
        self.assertEqual(self.request(f'/v1/memory-item/{memory.memory_id}','DELETE',token=api_fixture.ALICE_TOKEN,headers=headers)[0],409)
        self.assertEqual(self.engine.list_memories('alice'),[changed])
        for invalid in (None,True,'','a'*64+'\n'):
            body={'memory_id':memory.memory_id,'content':'New text','expected_revision':invalid}
            self.assertEqual(self.request('/v1/memory','PATCH',body,api_fixture.ALICE_TOKEN)[0],400)

    def test_legacy_callers_remain_supported_and_new_revision_success(self):
        memory=self.engine.list_memories('alice')[0]
        body={'memory_id':memory.memory_id,'content':'Reviewed text','expected_revision':memory.revision}
        status,changed,_=self.request('/v1/memory','PATCH',body,api_fixture.ALICE_TOKEN)
        self.assertEqual(status,200);self.assertNotEqual(changed['memory']['revision'],memory.revision)
        body.pop('expected_revision');body['content']='Legacy explicit replacement'
        self.assertEqual(self.request('/v1/memory','PATCH',body,api_fixture.ALICE_TOKEN)[0],200)


if __name__=='__main__':unittest.main()
