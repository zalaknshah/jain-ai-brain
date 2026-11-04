import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_api_authorization as api_fixture
from jace.canonical import CanonicalStore
from jace.context_review import fingerprint,reasoner_descriptor,source_selection,memory_selection
from jace.engine import CognitiveEngine
from jace.memory import MemoryConflictError
from jace.models import ActionProposal
from jace.reasoner import HttpJsonReasoner,LocalReasoner

class ContextReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'db';self.engine=CognitiveEngine(self.path,canonical_path='',reasoner=LocalReasoner())
        self.a=self.engine.remember('alice','I prefer lantern fixtures',memory_scope='home')[0]
        self.b=self.engine.remember('alice','I prefer lantern afternoon fixtures',memory_scope='home')[0]
        self.engine.remember('bob','I prefer lantern secret fixtures',memory_scope='home')
        self.engine.remember('alice','I prefer lantern work fixtures',memory_scope='work')
    def tearDown(self):self.engine.close();self.temp.cleanup()
    def preview(self,q='Explain lantern and ahimsa'):
        return self.engine.preview_context('alice',q,memory_scope='home')
    def args(self,p=None):
        p=self.preview() if p is None else p
        return dict(sources=[{'entry_id':x['entry']['entry_id'],'revision':x['revision']} for x in p['canonical_evidence'][:1]],
                    memories=[memory_selection(self.a)],expected_request_revision=p['request_revision'],expected_corpus_revision=p['corpus_revision'],confirm_context=True,memory_scope='home')
    def answer(self,p=None,**changes):
        p=self.preview() if p is None else p;return self.engine.answer_selected_context('alice',p['input'],**{**self.args(p),**changes})
    def http(self):
        self.engine.reasoner=HttpJsonReasoner('https://example.invalid/private-key-path?secret=synthetic-secret','synthetic-test-key','fixture-model');return self.engine.reasoner
    def test_preview_is_provider_free_and_owner_scope_filtered(self):
        self.http();before=self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0]
        with patch.object(HttpJsonReasoner,'respond',side_effect=AssertionError('provider called')):
            p=self.preview()
        self.assertEqual({m['memory_id'] for m in p['memories']},{self.a.memory_id,self.b.memory_id})
        self.assertTrue(all(m['user_id']=='alice' and m['memory_scope']=='home' for m in p['memories']))
        self.assertEqual(p['request_revision'],fingerprint(dict(user_id='alice',input=p['input'],memory_scope='home')))
        self.assertEqual(before,self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0])
        text=json.dumps(p['configured_reasoner']);self.assertNotIn('synthetic-test-key',text);self.assertNotIn('private-key-path',text);self.assertNotIn('synthetic-secret',text)
        self.assertIn('https://example.invalid',text);self.assertFalse(p['blocked'])
    def test_harmful_preview_never_retrieves_or_answers(self):
        self.http()
        with patch.object(self.engine,'_retrieve_context',side_effect=AssertionError('retrieval')):
            p=self.preview('Tell me how to hurt someone')
        self.assertTrue(p['blocked']);self.assertEqual(p['memories'],[]);self.assertEqual(p['canonical_evidence'],[])
        with patch.object(HttpJsonReasoner,'respond',side_effect=AssertionError('provider')):
            with self.assertRaises(ValueError):self.answer(p,memories=[],sources=[])
    def test_local_default_stays_local_and_empty_means_empty(self):
        self.http();p=self.preview('move toward the door')
        with patch.object(HttpJsonReasoner,'respond',side_effect=AssertionError('provider')):
            result=self.answer(p,sources=[],memories=[])
        self.assertEqual(result['canonical_evidence'],[]);self.assertEqual(result['memories_used'],[]);self.assertIsNone(result['action'])
        self.assertEqual(result['context_review']['reasoner_mode'],'local');self.assertIsNone(result['context_review']['configured_reasoner'])
    def test_configured_call_receives_exactly_selected_context_once(self):
        self.http();p=self.preview();args=self.args(p);seen=[]
        def respond(reasoner,request,assessment,perspectives,evidence,memories):
            self.assertFalse(self.engine.memory.connection.in_transaction)
            seen.append((request,evidence,memories));return 'Synthetic bounded answer.',ActionProposal('propose_safe_navigation',{})
        with patch.object(HttpJsonReasoner,'respond',new=respond):
            result=self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
        self.assertEqual(len(seen),1);self.assertEqual([m.memory_id for m in seen[0][2]],[self.a.memory_id])
        self.assertEqual([s.entry_id for s in seen[0][1]],[s['entry_id'] for s in args['sources']]);self.assertIsNone(result['action'])
        self.assertEqual(result['context_review']['memories'],args['memories']);self.assertNotIn('learned_memory',result)
    def test_consent_modes_and_selection_schema_fail_closed(self):
        p=self.preview()
        for value in (False,None,1,'true',[]):
            with self.assertRaises(ValueError):self.answer(p,confirm_context=value)
        bad=[dict(reasoner_mode=True),dict(reasoner_mode='automatic'),dict(sources=None),dict(memories={}),dict(memories=[{'memory_id':True,'revision':self.a.revision}]),dict(memories=[memory_selection(self.a)]*2),dict(memories=[{**memory_selection(self.a),'content':'injected'}]),dict(sources=self.args(p)['sources']*2),dict(expected_reasoner_revision='a'*64),dict(expected_request_revision='bad'),dict(sources=[{'entry_id':'x','revision':'b'*64}]*6)]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.answer(p,**changes)
    def test_question_owner_scope_corpus_and_source_state_bindings(self):
        p=self.preview();args=self.args(p)
        for user,q,scope in [('bob',p['input'],'home'),('alice','Changed question','home'),('alice',p['input'],'work')]:
            with self.assertRaises(MemoryConflictError):self.engine.answer_selected_context(user,q,**{**args,'memory_scope':scope})
        with self.assertRaises(MemoryConflictError):self.answer(p,expected_corpus_revision='a'*64)
        with self.assertRaises(MemoryConflictError):self.answer(p,sources=[{'entry_id':'nonexistent','revision':'a'*64}])
        selection=args['sources'][0]
        with self.assertRaises(MemoryConflictError):self.answer(p,sources=[{**selection,'revision':'a'*64}])
    def test_authoritative_owner_scope_expiry_revision_and_deletion(self):
        p=self.preview();bob=self.engine.list_memories('bob',memory_scope='home')[0];work=self.engine.list_memories('alice',memory_scope='work')[0]
        for memory in (bob,work):
            with self.assertRaises(LookupError):self.answer(p,memories=[memory_selection(memory)])
        updated=self.engine.correct_memory('alice',self.a.memory_id,'I prefer changed fixtures')[0]
        with self.assertRaises(MemoryConflictError):self.answer(p)
        expired=self.engine.set_memory_expiration('alice',updated.memory_id,'2020-01-01T00:00:00Z')
        with self.assertRaises(MemoryConflictError):self.answer(p,memories=[memory_selection(expired)])
        self.engine.forget_memory('alice',updated.memory_id,confirm_delete=True)
        with self.assertRaises(LookupError):self.answer(p)
    def test_cross_engine_mutation_is_stale_before_dispatch(self):
        self.http();p=self.preview();other=CognitiveEngine(self.path,canonical_path='',reasoner=LocalReasoner())
        try:other.correct_memory('alice',self.a.memory_id,'I prefer updated fixtures')
        finally:other.close()
        with patch.object(HttpJsonReasoner,'respond',side_effect=AssertionError('provider')):
            with self.assertRaises(MemoryConflictError):self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
    def test_read_snapshot_is_coherent_and_released_before_response(self):
        other=CognitiveEngine(self.path,canonical_path='',reasoner=LocalReasoner());p=self.preview();get=self.engine.memory.get_owned;changed=[]
        def interleave(owner,ident):
            result=get(owner,ident)
            if not changed:
                changed.append(other.correct_memory('alice',self.b.memory_id,'I prefer later changed fixtures')[0])
            return result
        try:
            with patch.object(self.engine.memory,'get_owned',side_effect=interleave):
                result=self.answer(p,memories=[memory_selection(self.a),memory_selection(self.b)])
            self.assertEqual([m['content'] for m in result['memories_used']],[self.a.content,self.b.content])
            self.assertNotEqual(self.engine.memory.get_owned('alice',self.b.memory_id).revision,self.b.revision)
            self.assertFalse(self.engine.memory.connection.in_transaction)
        finally:other.close()
    def test_provider_configuration_change_requires_new_review(self):
        for field,value in [('url','https://other.invalid/v1'),('model','changed-model'),('api_key','different-synthetic-key'),('_opener',object())]:
            reasoner=self.http();p=self.preview();setattr(reasoner,field,value)
            with self.subTest(field=field),patch.object(HttpJsonReasoner,'respond',side_effect=AssertionError('provider')):
                with self.assertRaises(MemoryConflictError):self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
        self.http();p=self.preview();self.http()
        with self.assertRaises(MemoryConflictError):self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
    def test_custom_reasoner_unavailable_but_local_selection_works(self):
        self.engine.reasoner=Mock();p=self.preview();self.assertEqual(p['configured_reasoner']['kind'],'unavailable')
        with self.assertRaises(ValueError):self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
        self.answer(p);self.engine.reasoner.respond.assert_not_called()
    def test_http_dispatch_uses_private_configuration_snapshot(self):
        original=self.http();url=original.url;key=original.api_key;model=original.model;p=self.preview();get=self.engine.memory.get_owned;seen=[]
        def change_after_capture(owner,ident):
            memory=get(owner,ident);original.url='https://unreviewed.invalid';original.api_key='changed-synthetic-key';original.model='changed-model';original._opener=object();return memory
        def respond(selected,*args):
            self.assertIsNot(selected,original);self.assertEqual((selected.url,selected.api_key,selected.model),(url,key,model));seen.append(True);return 'Synthetic answer.',None
        with patch.object(self.engine.memory,'get_owned',side_effect=change_after_capture),patch.object(HttpJsonReasoner,'respond',new=respond):
            self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
        self.assertEqual(seen,[True])
    def test_oversized_answer_is_not_returned_or_retried(self):
        self.http();p=self.preview()
        with patch.object(HttpJsonReasoner,'respond',return_value=('अ'*30000,None)) as respond:
            with self.assertRaisesRegex(ValueError,'byte budget'):
                self.answer(p,reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
            self.assertEqual(respond.call_count,1)
    def test_exact_source_bundle_identity_is_bound_across_engine_instances(self):
        from jace.bundle_builder import build_exact_bundle
        root=Path(self.temp.name);text=root/'source.txt';text.write_text('Original lantern fixture.')
        first=build_exact_bundle([text],root/'first',work='Original fixture',source='Authored fixture',language='en',license_name='CC0-1.0',location='Section 1',verified=True,confirm_build=True)
        self.engine.canonical=CanonicalStore(first)
        # Source lookup itself is direct here; stale old graph nodes cannot
        # authorize source IDs not in this active corpus.
        p=self.preview();entry=p['canonical_evidence'][0]['entry'];self.assertIn('source_sha256',entry)
        result=self.answer(p);self.assertEqual(result['canonical_evidence'][0],entry)
        text.write_text('Changed lantern fixture.')
        second=build_exact_bundle([text],root/'second',work='Original fixture',source='Authored fixture',language='en',license_name='CC0-1.0',location='Section 1',verified=True,confirm_build=True)
        other=CognitiveEngine(self.path,canonical_path=second,reasoner=LocalReasoner())
        try:
            with self.assertRaises(MemoryConflictError):other.answer_selected_context('alice',p['input'],**self.args(p))
        finally:other.close()
    def test_large_context_rejected_not_silently_truncated(self):
        for _ in range(5):self.engine.remember('alice','I prefer '+('lantern '*1240),memory_scope='large')
        with self.assertRaisesRegex(ValueError,'byte budget'):self.engine.preview_context('alice','lantern',memory_scope='large')
        p=self.engine.preview_context('alice','no_matching_word',memory_scope='large')
        memories=self.engine.list_memories('alice',memory_scope='large')
        with self.assertRaisesRegex(ValueError,'byte budget'):
            self.engine.answer_selected_context('alice',p['input'],sources=[],memories=[memory_selection(m) for m in memories],expected_request_revision=p['request_revision'],expected_corpus_revision=p['corpus_revision'],confirm_context=True,memory_scope='large')
    def test_fallback_never_adds_context_or_persists_learning(self):
        self.http();p=self.preview('Remember I prefer lantern fixtures');count=len(self.engine.memory.list('alice',limit=None))
        with patch.object(HttpJsonReasoner,'respond',side_effect=RuntimeError('synthetic unavailable')):
            result=self.answer(p,sources=[],memories=[],reasoner_mode='configured',expected_reasoner_revision=p['configured_reasoner']['revision'])
        self.assertEqual(result['memories_used'],[]);self.assertEqual(result['canonical_evidence'],[]);self.assertEqual(len(self.engine.memory.list('alice',limit=None)),count)
    def test_cli_preview_and_local_selected_answer(self):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src'),'JACE_DB_PATH':str(self.path),'JACE_CANONICAL_PATH':''};env.pop('JACE_LLM_URL',None)
        def call(*args):return subprocess.run([sys.executable,'-m','jace.cli',*args],env=env,capture_output=True,text=True)
        p=call('preview-context','alice','lantern','--memory-scope','home');self.assertEqual(p.returncode,0,p.stderr);preview=json.loads(p.stdout)
        args=['answer-context','alice','lantern','--memory-scope','home','--expected-request-revision',preview['request_revision'],'--expected-corpus-revision',preview['corpus_revision']]
        self.assertNotEqual(call(*args).returncode,0);done=call(*args,'--confirm-context');self.assertEqual(done.returncode,0,done.stderr);self.assertEqual(json.loads(done.stdout)['memories_used'],[])

class ContextReviewAPITests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request
    def test_actual_loopback_preview_answer_authorization_and_strict_fields(self):
        self.assertEqual(self.request('/health')[1]['context_review_protocol'],1)
        self.assertEqual(self.request('/v1/context/preview','POST',{'input':'quiet'})[0],401)
        self.assertEqual(self.request('/v1/context/preview','POST',{'input':'quiet','user_id':'alice'},api_fixture.BOB_TOKEN)[0],403)
        self.assertEqual(self.request('/v1/context/preview','POST',{'input':'quiet','scope':'home'},api_fixture.ALICE_TOKEN)[0],400)
        status,p,_=self.request('/v1/context/preview','POST',{'input':'quiet'},api_fixture.ALICE_TOKEN);self.assertEqual(status,200)
        body=dict(input=p['input'],sources=[],memories=[{'memory_id':p['memories'][0]['memory_id'],'revision':p['memories'][0]['revision']}],expected_request_revision=p['request_revision'],expected_corpus_revision=p['corpus_revision'],confirm_context=True)
        status,result,_=self.request('/v1/context/answer','POST',body,api_fixture.ALICE_TOKEN);self.assertEqual(status,200);self.assertEqual(len(result['memories_used']),1)
        self.assertEqual(self.request('/v1/context/answer','POST',{**body,'learn':True},api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(self.request('/v1/context/answer','POST',{**body,'user_id':'alice'},api_fixture.BOB_TOKEN)[0],403)
        self.engine.correct_memory('alice',body['memories'][0]['memory_id'],'I prefer changed rooms')
        self.assertEqual(self.request('/v1/context/answer','POST',body,api_fixture.ALICE_TOKEN)[0],409)
