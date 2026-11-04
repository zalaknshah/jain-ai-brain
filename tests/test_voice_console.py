import os
import shutil
import subprocess
import unittest
from pathlib import Path
import test_api_authorization as api_fixture
from jace.reasoner import LocalReasoner


@unittest.skipUnless(shutil.which("node"), "Node.js required for browser script harness")
class VoiceConsoleTests(unittest.TestCase):
    def run_scenario(self, name):
        harness = Path(__file__).with_name("web_console_harness.js")
        result = subprocess.run(["node", str(harness), name], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_binding_retained_identity(self):self.run_scenario('binding_retained_identity')
    def test_binding_silent_health(self):self.run_scenario('binding_silent_health')
    def test_binding_silent_reply(self):self.run_scenario('binding_silent_reply')
    def test_binding_transcript_identity(self):self.run_scenario('binding_transcript_identity')
    def test_binding_transcript_draft(self):self.run_scenario('binding_transcript_draft')
    def test_binding_read_identity(self):self.run_scenario('binding_read_identity')
    def test_binding_pending_playback_identity(self):self.run_scenario('binding_pending_playback_identity')
    def test_binding_reset_rebind(self):self.run_scenario('binding_reset_rebind')
    def test_binding_learning_snapshot(self):self.run_scenario('binding_learning_snapshot')
    def test_binding_restored_learning(self):self.run_scenario('binding_restored_learning')
    def test_binding_page_lifecycle(self):self.run_scenario('binding_page_lifecycle')
    def test_binding_question_during_health(self):self.run_scenario('binding_question_during_health')
    def test_binding_stream_change(self):self.run_scenario('binding_stream_change')
    def test_binding_origin_validation(self):self.run_scenario('binding_origin_validation')
    def test_binding_transport_options(self):self.run_scenario('binding_transport_options')
    def test_binding_response_bounds(self):self.run_scenario('binding_response_bounds')
    def test_binding_reply_context(self):self.run_scenario('binding_reply_context')
    def test_binding_consumed_invalid_learning(self):self.run_scenario('binding_consumed_invalid_learning')
    def test_binding_preflight_cancel(self):self.run_scenario('binding_preflight_cancel')

    def test_transcript_requires_review_before_send(self): self.run_scenario('transcript')
    def test_repeated_interrupted_and_denied_recognition(self): self.run_scenario('recognition_lifecycle')
    def test_new_request_ignores_old_response_and_audio(self): self.run_scenario('stale')
    def test_cancel_cannot_display_late_response(self): self.run_scenario('cancel')
    def test_matching_voice_and_playback_interruption(self): self.run_scenario('speech')
    def test_cancel_pending_playback_while_microphone_ends(self): self.run_scenario('pending_playback_cancel')
    def test_identity_change_hides_late_private_response(self): self.run_scenario('identity_change')
    def test_destination_change_drops_previous_draft_and_token(self): self.run_scenario('destination_change')
    def test_scope_change_clears_context_and_ignores_late_callbacks(self): self.run_scenario('scope_change')
    def test_scope_capability_check_precedes_question_transmission(self): self.run_scenario('scope_capability')
    def test_scope_validation_and_server_echo_fail_closed(self): self.run_scenario('scope_validation')
    def test_page_exit_ignores_late_response(self): self.run_scenario('pagehide')
    def test_text_works_without_browser_audio(self): self.run_scenario('unsupported')


@unittest.skipUnless(shutil.which("node"), "Node.js required for synthetic loopback")
class ConsoleLoopbackTests(unittest.TestCase):
    tearDown=api_fixture.ApiAuthorizationTests.tearDown
    def setUp(self):
        api_fixture.ApiAuthorizationTests.setUp(self)
        self.engine.reasoner=LocalReasoner()  # Explicit local template, no provider.
        self.original=self.engine.list_memories('alice')
    def run_client(self,scenario):
        result=subprocess.run(['node',str(Path(__file__).with_name('web_console_harness.js')),scenario],env={**os.environ,'JACE_TEST_API':f'http://127.0.0.1:{self.server.server_port}'},capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_actual_streaming_question_and_one_use_learning(self):
        self.run_client('real_ask_learning')
        self.assertEqual(len(self.engine.list_memories('alice',memory_scope='home')),1)
        self.assertEqual(self.engine.list_memories('alice',memory_scope='default'),self.original)
    def test_actual_wrong_owner_cannot_learn(self):
        self.run_client('real_wrong_owner')
        self.assertEqual(self.engine.list_memories('alice'),self.original)
        self.assertEqual(self.engine.list_memories('bob'),[])
