import os
from pathlib import Path
import shutil
import subprocess
import unittest
import test_dispute_preparation as fixture


@unittest.skipUnless(shutil.which('node'),'Node.js required for script fixtures, not real-browser QA')
class DisputeScreenTests(unittest.TestCase):
    def scenario(self,name):
        result=subprocess.run(['node',str(Path(__file__).with_name('dispute_preparation_harness.js')),name],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_local_review_and_single_use_transmission(self):self.scenario('local_review_then_one_send')
    def test_edits_and_option_counts_invalidate_review(self):self.scenario('editing_and_dynamic_options_invalidate')
    def test_invalid_fields_and_destinations_stay_local(self):self.scenario('invalid_fields_and_destination_before_network')
    def test_silent_changes_before_submit(self):self.scenario('silent_changes_before_submit')
    def test_silent_identity_cannot_rebind_old_draft_or_result(self):self.scenario('silent_identity_cannot_rebind_existing_draft')
    def test_change_event_clears_identity_bound_private_fields(self):self.scenario('identity_change_event_clears_private_fields')
    def test_silent_identity_change_during_health(self):self.scenario('silent_identity_during_health')
    def test_silent_option_change_during_health(self):self.scenario('silent_draft_during_health')
    def test_silent_identity_change_during_body_stream(self):self.scenario('silent_identity_during_body_stream')
    def test_silent_draft_change_after_submission_suppresses_result(self):self.scenario('silent_draft_during_post_suppresses_result')
    def test_cancel_suppresses_late_response_and_retry(self):self.scenario('cancel_late_response_and_no_retry')
    def test_protocol_and_network_errors_never_retry_or_echo(self):self.scenario('protocol_failure_and_network_failure_no_retry')
    def test_exact_echo_and_no_action_provider_save_verification_flags(self):self.scenario('report_binding_and_outcome_flags')
    def test_text_only_risk_notice_and_page_lifecycle_clear(self):self.scenario('text_only_rendering_risk_and_lifecycle_reset')
    def test_response_byte_and_utf8_bounds(self):self.scenario('oversized_and_invalid_utf8_responses')


@unittest.skipUnless(shutil.which('node'),'Node.js required for synthetic JS-to-Python loopback tests')
class DisputeScreenLoopbackTests(unittest.TestCase):
    setUp=fixture.DisputeAPITests.setUp
    tearDown=fixture.DisputeAPITests.tearDown
    def scenario(self,name):
        changes=self.engine.memory.connection.total_changes
        before=self.engine.list_memories('alice')
        result=subprocess.run(['node',str(Path(__file__).with_name('dispute_preparation_harness.js')),name],
            env={**os.environ,'JACE_TEST_API':f'http://127.0.0.1:{self.server.server_port}'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.engine.memory.connection.total_changes,changes)
        self.assertEqual(self.engine.list_memories('alice'),before)
        self.reasoner.respond.assert_not_called()
    def test_real_explicit_comparison_and_declared_deadline_without_save(self):self.scenario('real_valid_flags_and_no_persistence')
    def test_real_casefold_rejection_and_explicit_recovery(self):self.scenario('real_unicode_authoritative_rejection_and_recovery')


if __name__=='__main__':unittest.main()
