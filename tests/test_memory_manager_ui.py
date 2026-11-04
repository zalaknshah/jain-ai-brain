import os
import shutil
import subprocess
import unittest
from pathlib import Path
import test_api_authorization as api_fixture


@unittest.skipUnless(shutil.which('node'), 'Node.js required for browser-script fixture tests')
class MemoryManagerUITests(unittest.TestCase):
    def scenario(self,name):
        result=subprocess.run(['node',str(Path(__file__).with_name('memory_manager_harness.js')),name],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_review_and_explicit_revision_checked_correction(self):self.scenario('review_correct')
    def test_typed_profile_blocks_generic_edit_but_retains_expiry(self):self.scenario('typed_profile')
    def test_typed_inventory_blocks_generic_edit_but_retains_expiry(self):self.scenario('typed_inventory')
    def test_explicit_expiration_and_renewal(self):self.scenario('expiry')
    def test_separate_consumed_deletion_choices_and_no_double_submit(self):self.scenario('delete_choices')
    def test_identity_change_discards_late_private_page(self):self.scenario('stale_identity')
    def test_destination_change_during_health_prevents_private_request(self):self.scenario('changed_during_health')
    def test_cancelled_mutation_is_uncertain_not_retried(self):self.scenario('cancel_uncertain_write')
    def test_conflict_clears_selection_and_does_not_retry(self):self.scenario('conflict_no_retry')
    def test_paging_replaces_view_and_uses_exact_cursor(self):self.scenario('pagination')
    def test_mismatched_scope_fails_closed_and_content_is_text(self):self.scenario('wrong_scope_and_xss')
    def test_unsafe_destination_and_old_protocol_fail_closed(self):self.scenario('validation_and_protocol')
    def test_page_exit_clears_credentials_and_unsaved_draft(self):self.scenario('pagehide_and_draft')
    def test_streamed_response_byte_limit(self):self.scenario('oversized_response')


@unittest.skipUnless(shutil.which('node'), 'Node.js required for actual loopback client integration')
class MemoryManagerLoopbackTests(unittest.TestCase):
    tearDown=api_fixture.ApiAuthorizationTests.tearDown

    def setUp(self):
        api_fixture.ApiAuthorizationTests.setUp(self)
        self.home=self.engine.remember('alice','Original home fixture',memory_scope='home')[0]
        self.work=self.engine.remember('alice','Preserved work fixture',memory_scope='work')[0]
        self.bob=self.engine.remember('bob','Preserved Bob fixture',memory_scope='home')[0]
        for _ in range(2):
            self.engine.memory.connection.execute("INSERT INTO memory_audit(user_id,content,accepted,reason,created_at) VALUES ('alice',NULL,0,'Synthetic legacy fixture','2000-01-01')")
        self.engine.memory.connection.commit()

    def run_client(self,scenario):
        env={**os.environ,'JACE_TEST_API':f'http://127.0.0.1:{self.server.server_port}'}
        result=subprocess.run(['node',str(Path(__file__).with_name('memory_manager_harness.js')),scenario],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_streaming_http_review_correction_expiry_and_confirmed_delete(self):
        self.run_client('real_lifecycle')
        self.assertEqual(self.engine.list_memories('alice',memory_scope='home'),[])
        self.assertEqual(self.engine.list_memories('alice',memory_scope='work'),[self.work])
        self.assertEqual(self.engine.list_memories('bob',memory_scope='home'),[self.bob])
        self.assertEqual(len(self.engine.list_memories('alice')),1)
        self.assertEqual(self.engine.memory.connection.execute("SELECT COUNT(*) FROM memory_audit WHERE user_id='alice' AND memory_id IS NULL").fetchone()[0],0)

    def test_actual_conflicting_client_update_does_not_get_overwritten(self):
        self.run_client('real_conflict')
        self.assertEqual(self.engine.memory.get_owned('alice',self.home.memory_id).content,'Another client changed this memory')

    def test_actual_other_owner_cannot_load_page(self):
        self.run_client('real_owner_isolation')
        self.assertEqual(self.engine.list_memories('alice',memory_scope='home'),[self.home])


if __name__=='__main__':unittest.main()
