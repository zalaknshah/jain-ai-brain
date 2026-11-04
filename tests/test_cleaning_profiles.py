import json
import os
import subprocess
import sys
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_api_authorization as api_fixture
from jace.cleaning import PROFILE_SOURCE, build_plan, decode_profile, encode_profile, validate_profile
from jace.engine import CognitiveEngine
from jace.memory import MemoryConflictError
from jace.reasoner import LocalReasoner

PROFILE={'surface':'wooden_furniture','water_policy':'avoid','time_budget_minutes':10,'supplies_policy':'existing_only'}


class CleaningProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.engine=CognitiveEngine(Path(self.temp.name)/'db',canonical_path='',reasoner=LocalReasoner())

    def tearDown(self):self.engine.close();self.temp.cleanup()

    def save(self,profile=None,user='alice',**kwargs):
        return self.engine.save_cleaning_profile(user,PROFILE if profile is None else profile,confirm_save=True,**kwargs)[0]

    def test_confirmation_and_exact_schema_precede_persistence(self):
        for consent in (False,None,1,'true',[]):
            with self.assertRaises(ValueError):self.engine.save_cleaning_profile('alice',PROFILE,confirm_save=consent)
        bad=[{}, {**PROFILE,'extra':True}, {**PROFILE,'surface':'wood'}, {**PROFILE,'water_policy':'avoid '},
             {**PROFILE,'supplies_policy':None}]
        for minutes in (0,121,True,1.0,float('nan'),10**1000):bad.append({**PROFILE,'time_budget_minutes':minutes})
        for value in bad:
            with self.assertRaises(ValueError):self.save(value)
        self.assertEqual(self.engine.list_memories('alice'),[])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],0)

    def test_typed_choices_change_practical_steps_without_model_or_actions(self):
        memory=self.save();reasoner=Mock();self.engine.reasoner=reasoner
        result=self.engine.plan_cleaning('alice')
        self.assertEqual(result['status'],'planned');self.assertEqual(result['profile_applied'],PROFILE)
        text=' '.join(step['instruction'] for step in result['steps'])
        for phrase in ('wooden furniture','Keep water and liquid cleaning products out','already-owned','at most 10 minute','Do not mix','contamination','pause'):
            self.assertIn(phrase,text)
        self.assertEqual(result['profile_memory']['memory_id'],memory.memory_id)
        self.assertIn('no reviewed canonical passage',result['grounding'])
        self.assertIsNone(result['action']);self.assertFalse(result['actions_executed']);reasoner.respond.assert_not_called()
        alternate={**PROFILE,'surface':'hard_floor','water_policy':'follow_surface_guidance','time_budget_minutes':1,'supplies_policy':'review_missing'}
        changed=self.engine.update_cleaning_profile('alice',memory.memory_id,alternate,expected_revision=memory.revision,confirm_save=True)[0]
        result=self.engine.plan_cleaning('alice',profile_memory_id=changed.memory_id)
        text=' '.join(step['instruction'] for step in result['steps'])
        self.assertIn('does not establish that water',text);self.assertIn('neither orders nor authorizes',text);self.assertIn('at most 1 minute',text)
        self.assertNotIn('Keep water and liquid',text);reasoner.respond.assert_not_called()

    def test_every_allowed_profile_preserves_safety_and_template_limits(self):
        for surface in ('wooden_furniture','hard_floor','general'):
            for water in ('avoid','follow_surface_guidance'):
                for supplies in ('existing_only','review_missing'):
                    for minutes in (1,120):
                        plan=build_plan(validate_profile(dict(surface=surface,water_policy=water,supplies_policy=supplies,time_budget_minutes=minutes)))
                        text=' '.join(step['instruction'] for step in plan['steps'])
                        self.assertIn('Do not mix cleaning products',text);self.assertIn('disinfection',text)
                        self.assertIn('not a claim that the task can be completed',text)
                        self.assertIn('qualified guidance',text);self.assertIsNone(plan['action'])
                        self.assertIn('Authored conditional checklist',plan['limits'][0])

    def test_no_inference_or_silent_conflict_resolution(self):
        self.engine.remember('alice',encode_profile(validate_profile(PROFILE)))
        self.engine.remember('alice',"Remember, we shouldn't wipe wooden furniture with water.")
        self.assertEqual(self.engine.plan_cleaning('alice')['status'],'needs_profile')
        first=self.save();second=self.save({**PROFILE,'water_policy':'follow_surface_guidance'})
        result=self.engine.plan_cleaning('alice')
        self.assertEqual(result['status'],'choose_profile');self.assertEqual(result['steps'],[])
        self.assertEqual({p['memory_id'] for p in result['profiles']},{first.memory_id,second.memory_id})
        self.assertEqual(self.engine.plan_cleaning('alice',profile_memory_id=first.memory_id)['profile_applied']['water_policy'],'avoid')

    def test_scope_owner_expiry_and_deletion_boundaries(self):
        home=self.save(memory_scope='home');work=self.save(memory_scope='work');bob=self.save(user='bob',memory_scope='home')
        for owner,scope,memory_id in [('alice','home',bob.memory_id),('alice','home',work.memory_id),('alice','default',home.memory_id)]:
            with self.assertRaises(LookupError):self.engine.plan_cleaning(owner,memory_scope=scope,profile_memory_id=memory_id)
        self.assertEqual(self.engine.plan_cleaning('alice')['status'],'needs_profile')
        expiry='2030-01-01T00:00:00.000000+00:00'
        self.engine.set_memory_expiration('alice',home.memory_id,expiry)
        with patch('jace.engine.recall_time',return_value=expiry):
            self.assertEqual(self.engine.plan_cleaning('alice',memory_scope='home')['status'],'needs_profile')
            with self.assertRaises(LookupError):self.engine.plan_cleaning('alice',memory_scope='home',profile_memory_id=home.memory_id)
        self.engine.set_memory_expiration('alice',home.memory_id,None)
        self.assertEqual(self.engine.plan_cleaning('alice',memory_scope='home')['status'],'planned')
        self.engine.forget_memory('alice',home.memory_id,confirm_delete=True)
        self.assertEqual(self.engine.plan_cleaning('alice',memory_scope='home')['status'],'needs_profile')
        self.assertEqual(self.engine.plan_cleaning('alice',memory_scope='work')['profile_memory']['memory_id'],work.memory_id)
        self.assertEqual(self.engine.plan_cleaning('bob',memory_scope='home')['profile_memory']['memory_id'],bob.memory_id)

    def test_stale_typed_update_and_generic_correction_cannot_mutate_profile(self):
        memory=self.save();new=self.engine.update_cleaning_profile('alice',memory.memory_id,{**PROFILE,'time_budget_minutes':20},expected_revision=memory.revision,confirm_save=True)[0]
        with self.assertRaises(MemoryConflictError):self.engine.update_cleaning_profile('alice',memory.memory_id,PROFILE,expected_revision=memory.revision,confirm_save=True)
        with self.assertRaises(ValueError):self.engine.correct_memory('alice',memory.memory_id,'Different plain text',expected_revision=new.revision)
        for revision in (None,'',True):
            with self.assertRaises(ValueError):self.engine.update_cleaning_profile('alice',memory.memory_id,PROFILE,expected_revision=revision,confirm_save=True)
        self.assertEqual(self.engine.memory.get_owned('alice',memory.memory_id),new)
        ordinary=self.engine.remember('alice',encode_profile(validate_profile(PROFILE)))[0]
        with self.assertRaises(ValueError):self.engine.update_cleaning_profile('alice',ordinary.memory_id,PROFILE,expected_revision=ordinary.revision,confirm_save=True)

    def test_save_and_update_graph_failures_roll_back_all_owned_state(self):
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.save()
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],0)
        memory=self.save()
        with patch.object(self.engine.graph,'add_memory',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.engine.update_cleaning_profile('alice',memory.memory_id,{**PROFILE,'time_budget_minutes':20},expected_revision=memory.revision,confirm_save=True)
        self.assertEqual(self.engine.memory.get_owned('alice',memory.memory_id),memory)
        self.assertIsNotNone(self.engine.memory.connection.execute('SELECT node_id FROM graph_nodes WHERE node_id=?',(f'memory:{memory.memory_id}',)).fetchone())

    def test_malformed_active_profile_blocks_guessing_and_can_be_explicitly_repaired(self):
        memory=self.save();self.save({**PROFILE,'time_budget_minutes':20})
        self.engine.memory.connection.execute('UPDATE memories SET content=? WHERE id=?',('{"version":1,"version":1,"profile":{}}',memory.memory_id));self.engine.memory.connection.commit()
        with self.assertRaises(ValueError):self.engine.plan_cleaning('alice')
        damaged=self.engine.memory.get_owned('alice',memory.memory_id)
        fixed=self.engine.update_cleaning_profile('alice',memory.memory_id,PROFILE,expected_revision=damaged.revision,confirm_save=True)[0]
        self.assertEqual(decode_profile(fixed).to_dict(),PROFILE)

    def test_candidate_limits_fail_closed_but_explicit_selection_is_bounded(self):
        first=self.save()
        for _ in range(25):self.save()
        with self.assertRaisesRegex(ValueError,'too many'):self.engine.plan_cleaning('alice')
        self.assertEqual(self.engine.plan_cleaning('alice',profile_memory_id=first.memory_id)['status'],'planned')
        for value in (0,True,-1,2**63,'1'):
            with self.assertRaises(ValueError):self.engine.plan_cleaning('alice',profile_memory_id=value)

    def test_cli_preview_save_plan_and_revision_checked_update_are_offline(self):
        root=Path(__file__).resolve().parents[1]
        env={**os.environ,'PYTHONPATH':str(root/'src'),'JACE_DB_PATH':str(Path(self.temp.name)/'cli.db'),
             'JACE_CANONICAL_PATH':'','JACE_LLM_URL':'intentionally-invalid-never-load-a-provider'}
        def run(*args):
            result=subprocess.run([sys.executable,'-m','jace.cli',*args],cwd=root,env=env,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            return json.loads(result.stdout)
        options=['--surface','wooden_furniture','--water-policy','avoid','--time-budget-minutes','10','--supplies-policy','existing_only']
        preview=run('save-cleaning-profile','alice',*options,'--memory-scope','home')
        self.assertFalse(preview['saved'])
        self.assertEqual(run('plan-cleaning','alice','--memory-scope','home')['status'],'needs_profile')
        saved=run('save-cleaning-profile','alice',*options,'--memory-scope','home','--confirm-save')['memory']
        plan=run('plan-cleaning','alice','--memory-scope','home')
        self.assertEqual(plan['profile_applied'],PROFILE);self.assertFalse(plan['actions_executed'])
        updated=run('update-cleaning-profile','alice',str(saved['memory_id']),*options,
                    '--expected-revision',saved['revision'],'--confirm-save')
        self.assertTrue(updated['saved'])
        self.assertEqual(run('plan-cleaning','alice')['status'],'needs_profile')

    def test_two_engine_profile_updates_from_same_revision_have_one_winner(self):
        memory=self.save();other=CognitiveEngine(Path(self.temp.name)/'db',canonical_path='',reasoner=LocalReasoner())
        barrier=threading.Barrier(2);outcomes=[]
        def change(engine,minutes):
            barrier.wait()
            try:
                engine.update_cleaning_profile('alice',memory.memory_id,{**PROFILE,'time_budget_minutes':minutes},
                    expected_revision=memory.revision,confirm_save=True)
                outcomes.append('updated')
            except MemoryConflictError:outcomes.append('conflict')
        try:
            threads=[threading.Thread(target=change,args=(self.engine,20)),threading.Thread(target=change,args=(other,30))]
            for thread in threads:thread.start()
            for thread in threads:thread.join(timeout=3);self.assertFalse(thread.is_alive())
            self.assertEqual(sorted(outcomes),['conflict','updated'])
        finally:other.close()


class CleaningProfileApiTests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request

    def test_explicit_owned_api_lifecycle_and_stale_update(self):
        body={'profile':PROFILE,'confirm_save':True,'memory_scope':'home'}
        status,data,_=self.request('/v1/cleaning-profiles','POST',body,api_fixture.ALICE_TOKEN)
        self.assertEqual(status,201);memory=data['memory'];self.assertEqual(memory['source'],PROFILE_SOURCE)
        request={'memory_scope':'home','profile_memory_id':memory['memory_id']}
        self.assertEqual(self.request('/v1/plans/cleaning','POST',request,api_fixture.BOB_TOKEN)[0],404)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',request,api_fixture.ALICE_TOKEN)[1]['status'],'planned')
        update={'memory_id':memory['memory_id'],'profile':{**PROFILE,'time_budget_minutes':20},'expected_revision':memory['revision'],'confirm_save':True}
        self.assertEqual(self.request('/v1/cleaning-profiles','PATCH',update,api_fixture.ALICE_TOKEN)[0],200)
        self.assertEqual(self.request('/v1/cleaning-profiles','PATCH',update,api_fixture.ALICE_TOKEN)[0],409)

    def test_malformed_fields_and_missing_consent_never_persist(self):
        for body in ({'profile':PROFILE},{'profile':PROFILE,'confirm_save':1},{'profile':PROFILE,'confirm_save':True,'scope':'home'},
                     {'profile':PROFILE,'confirm_save':True,'user_id':'bob'}):
            self.assertIn(self.request('/v1/cleaning-profiles','POST',body,api_fixture.ALICE_TOKEN)[0],(400,403))
        self.assertEqual(len(self.engine.list_memories('alice')),1)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',{'scope':'home'},api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',{'profile_memory_id':None},api_fixture.ALICE_TOKEN)[0],400)


if __name__=='__main__':unittest.main()
