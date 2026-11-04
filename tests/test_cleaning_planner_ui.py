import os
import shutil
import subprocess
import unittest
from pathlib import Path
import test_api_authorization as api_fixture
import test_cleaning_profiles as profile_fixture

@unittest.skipUnless(shutil.which('node'),'Node.js required for script fixtures')
class CleaningPlannerUITests(unittest.TestCase):
    def scenario(self,name):
        result=subprocess.run(['node',str(Path(__file__).with_name('cleaning_planner_harness.js')),name],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_create_review_then_explicit_plan(self):self.scenario('create_review_plan')
    def test_edit_resets_consent_and_blocks_unsaved_plan(self):self.scenario('edit_and_consumed_consent')
    def test_explicit_paged_profile_selection(self):self.scenario('explicit_paging_selection')
    def test_changed_destination_during_health_prevents_private_write(self):self.scenario('stale_health_boundary')
    def test_changed_identity_during_stream_ignores_private_body(self):self.scenario('stale_body_boundary')
    def test_uncertain_write_never_retried(self):self.scenario('uncertain_write_no_retry')
    def test_plan_revision_conflict_clears_selection(self):self.scenario('plan_conflict_no_retry')
    def test_invalid_fields_destinations_and_old_protocol_fail_closed(self):self.scenario('invalid_inputs_and_protocol')
    def test_mismatched_scope_revision_and_action_status_rejected(self):self.scenario('wrong_scope_and_actions')
    def test_text_rendering_scope_and_page_exit_privacy_reset(self):self.scenario('text_render_and_privacy_reset')
    def test_new_expiry_bound_with_offset_and_microsecond_precision(self):self.scenario('save_expiry_binding')
    def test_invalid_expiry_rejected_before_network(self):self.scenario('invalid_expiry_before_network')
    def test_updated_profile_preserves_reviewed_expiry(self):self.scenario('update_expiry_binding')
    def test_streaming_response_cap(self):self.scenario('oversized_response')
    def test_late_plan_ignored_after_cancel(self):self.scenario('stale_plan_after_cancel')

@unittest.skipUnless(shutil.which('node'),'Node.js required for actual loopback integration')
class CleaningPlannerLoopbackTests(unittest.TestCase):
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    def setUp(self):
        api_fixture.ApiAuthorizationTests.setUp(self)
        self.work=self.engine.remember('alice','Unrelated work fixture',memory_scope='work')[0]
        self.bob=self.engine.remember('bob','Unrelated Bob fixture',memory_scope='home')[0]
        # Any attempt to call a provider must fail the test.
        def forbidden(*args):raise AssertionError('Dedicated planner must never call a provider')
        self.engine.reasoner.respond=forbidden
    def run_client(self,name):
        result=subprocess.run(['node',str(Path(__file__).with_name('cleaning_planner_harness.js')),name],env={**os.environ,'JACE_TEST_API':f'http://127.0.0.1:{self.server.server_port}'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.engine.list_memories('alice',memory_scope='work'),[self.work])
        self.assertEqual(self.engine.list_memories('bob',memory_scope='home'),[self.bob])
    def saved_profile(self):return self.engine.save_cleaning_profile('alice',profile_fixture.PROFILE,confirm_save=True,memory_scope='home')[0]
    def test_real_create_reload_update_plan_without_provider(self):
        self.run_client('real_create_edit_plan')
        records=self.engine.list_memories('alice',memory_scope='home');self.assertEqual(len(records),1)
        self.assertIn('20',records[0].content)
    def test_real_conflict_before_plan_and_update(self):
        record=self.saved_profile();self.run_client('real_conflict')
        self.assertIn('40',self.engine.memory.get_owned('alice',record.memory_id).content)
    def test_real_expiration_and_wrong_owner_cannot_create(self):
        record=self.saved_profile();self.run_client('real_expiry_and_isolation')
        self.assertEqual(len(self.engine.list_memories('alice',memory_scope='home')),1)
        self.assertTrue(self.engine.memory.get_owned('alice',record.memory_id).expires_at.startswith('2000-'))

if __name__=='__main__':unittest.main()
