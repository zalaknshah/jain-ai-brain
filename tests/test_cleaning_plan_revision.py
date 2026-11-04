import unittest
from unittest.mock import patch
import test_api_authorization as api_fixture
import test_cleaning_profiles as profile_fixture
PROFILE=profile_fixture.PROFILE
from jace.memory import MemoryConflictError

class CleaningPlanRevisionTests(unittest.TestCase):
    setUp=profile_fixture.CleaningProfileTests.setUp
    tearDown=profile_fixture.CleaningProfileTests.tearDown
    save=profile_fixture.CleaningProfileTests.save

    def test_exact_snapshot_revision_rejects_stale_and_requires_explicit_id(self):
        memory=self.save(memory_scope='home')
        def plan(**kw):return self.engine.plan_cleaning('alice',memory_scope='home',**kw)
        self.assertEqual(plan(profile_memory_id=memory.memory_id,expected_profile_revision=memory.revision)['profile_memory'],memory.to_dict())
        with self.assertRaises(ValueError):plan(expected_profile_revision=memory.revision)
        for bad in (True,1,'A'*64,'a'*64+'\n','wrong'):
            with self.assertRaises(ValueError):plan(profile_memory_id=memory.memory_id,expected_profile_revision=bad)
        changed=self.engine.update_cleaning_profile('alice',memory.memory_id,{**PROFILE,'time_budget_minutes':20},expected_revision=memory.revision,confirm_save=True)[0]
        with self.assertRaises(MemoryConflictError):plan(profile_memory_id=memory.memory_id,expected_profile_revision=memory.revision)
        self.assertEqual(plan(profile_memory_id=memory.memory_id,expected_profile_revision=changed.revision)['profile_applied']['time_budget_minutes'],20)
        # Explicit omission preserves the earlier API's latest-row behavior.
        self.assertEqual(plan(profile_memory_id=memory.memory_id)['profile_applied']['time_budget_minutes'],20)

    def test_same_read_snapshot_used_when_another_engine_updates_after_read(self):
        from jace.engine import CognitiveEngine
        from jace.reasoner import LocalReasoner
        memory=self.save(memory_scope='home')
        other=CognitiveEngine(self.engine.memory.connection.execute('PRAGMA database_list').fetchone()[2],canonical_path='',reasoner=LocalReasoner())
        original=self.engine.memory.get_owned
        def racing_read(user,ident):
            row=original(user,ident)
            other.update_cleaning_profile(user,ident,{**PROFILE,'time_budget_minutes':21},expected_revision=row.revision,confirm_save=True)
            return row
        try:
            with patch.object(self.engine.memory,'get_owned',side_effect=racing_read):
                result=self.engine.plan_cleaning('alice',memory_scope='home',profile_memory_id=memory.memory_id,expected_profile_revision=memory.revision)
            self.assertEqual(result['profile_memory']['revision'],memory.revision)
            self.assertEqual(result['profile_applied']['time_budget_minutes'],10)
            self.assertNotEqual(original('alice',memory.memory_id).revision,memory.revision)
        finally:other.close()

class CleaningPlanRevisionAPITests(unittest.TestCase):
    setUp=api_fixture.ApiAuthorizationTests.setUp
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    request=api_fixture.ApiAuthorizationTests.request

    def test_health_and_strict_revision_route(self):
        self.assertEqual(self.request('/health')[1]['cleaning_planner_protocol'],1)
        memory=self.engine.save_cleaning_profile('alice',PROFILE,confirm_save=True,memory_scope='home')[0]
        body={'user_id':'alice','memory_scope':'home','profile_memory_id':memory.memory_id,'expected_profile_revision':memory.revision}
        self.assertEqual(self.request('/v1/plans/cleaning','POST',body,api_fixture.ALICE_TOKEN)[0],200)
        for bad in (None,True,'a'*64+'\n'):
            self.assertEqual(self.request('/v1/plans/cleaning','POST',{**body,'expected_profile_revision':bad},api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',{**body,'expected_profile_revision':'0'*64},api_fixture.ALICE_TOKEN)[0],409)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',{**body,'expected_revision':memory.revision},api_fixture.ALICE_TOKEN)[0],400)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',body,api_fixture.BOB_TOKEN)[0],403)
        self.assertEqual(self.request('/v1/plans/cleaning','POST',{**body,'memory_scope':'other'},api_fixture.ALICE_TOKEN)[0],404)
        self.engine.set_memory_expiration('alice',memory.memory_id,'2000-01-01T00:00:00Z')
        self.assertEqual(self.request('/v1/plans/cleaning','POST',body,api_fixture.ALICE_TOKEN)[0],404)

if __name__=='__main__':unittest.main()
