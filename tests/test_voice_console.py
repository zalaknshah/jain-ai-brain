import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js required for browser script harness")
class VoiceConsoleTests(unittest.TestCase):
    def run_scenario(self, name):
        harness = Path(__file__).with_name("web_console_harness.js")
        result = subprocess.run(["node", str(harness), name], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
