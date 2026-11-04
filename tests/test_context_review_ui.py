"""DOM-script fixtures; these do not launch or verify a real browser."""
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import test_api_authorization as api_fixture
from jace.reasoner import HttpJsonReasoner


@unittest.skipUnless(shutil.which('node'), 'Node.js required for script fixtures')
class ContextReviewUITests(unittest.TestCase):
    def scenario(self, name):
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('context_review_harness.js')), name],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_provider_free_preview_starts_unchecked(self): self.scenario('preview_only_unchecked')
    def test_selected_only_local_answer_and_consumed_consent(self): self.scenario('selected_only_local_and_consumed')
    def test_explicit_configured_mode_and_empty_selection(self): self.scenario('configured_explicit_and_empty_selection')
    def test_selection_changes_invalidate_consent(self): self.scenario('selection_invalidates_consent')
    def test_identity_scope_question_and_page_lifecycle_clear_private_context(self): self.scenario('changes_clear_private_context')
    def test_stale_health_prevents_preview_or_answer(self): self.scenario('stale_health_boundary')
    def test_stale_preview_response_is_discarded(self): self.scenario('stale_preview_response')
    def test_stale_stream_body_is_discarded(self): self.scenario('stale_stream_body')
    def test_silent_field_changes_fail_closed(self): self.scenario('silent_field_changes_fail_closed')
    def test_cancel_aborts_preview_and_answer_without_retry(self): self.scenario('cancel_preview_and_answer')
    def test_late_answer_after_identity_scope_or_question_change_is_discarded(self): self.scenario('stale_answer_changes')
    def test_failed_answer_requires_fresh_preview_and_never_retries(self): self.scenario('failed_answer_no_retry')
    def test_full_context_and_revision_receipt_binding(self): self.scenario('answer_binding_rejects_tampering')
    def test_configured_target_change_is_rejected(self): self.scenario('configured_target_binding')
    def test_malformed_wrong_scope_and_duplicate_candidates_rejected(self): self.scenario('invalid_preview_rejected')
    def test_blocked_preview_and_unavailable_configured_reasoner_fail_closed(self): self.scenario('blocked_and_unavailable')
    def test_untrusted_content_is_text_only_and_complete_source_digest_shown(self): self.scenario('untrusted_text_and_source_digest')
    def test_full_long_source_passage_and_target_metadata(self): self.scenario('long_source_metadata')
    def test_input_protocol_and_streaming_bounds(self): self.scenario('bounds_and_protocol')

    def test_retained_draft_identity_guard(self): self.scenario('retained_draft_identity_guard')

    def test_resets_cannot_rebind_token(self): self.scenario('resets_cannot_rebind_token')

    def test_restored_confirmation_rejected(self): self.scenario('restored_confirmation_rejected')

    def test_silent_selection_mode_rejected(self): self.scenario('silent_selection_mode_rejected')

    def test_silent_mode_during_health_rejected(self): self.scenario('silent_mode_during_health_rejected')

    def test_stream_stops_at_first_stale_chunk(self): self.scenario('stream_stops_at_first_stale_chunk')


@unittest.skipUnless(shutil.which('node'), 'Node.js required for actual loopback integration')
class ContextReviewLoopbackTests(unittest.TestCase):
    tearDown = api_fixture.ApiAuthorizationTests.tearDown

    def setUp(self):
        api_fixture.ApiAuthorizationTests.setUp(self)
        self.saved = self.engine.remember('alice', 'I prefer to clean gently without water.', memory_scope='home')[0]
        self.work = self.engine.remember('alice', 'Unrelated work: I clean gently.', memory_scope='work')[0]
        self.bob = self.engine.remember('bob', 'Unrelated Bob: I clean gently.', memory_scope='home')[0]
        self.engine.reasoner = HttpJsonReasoner('http://127.0.0.1:9/v1/respond', model='synthetic-unused')
        # No provider service exists or is contacted, even when HTTP is configured.
        self.no_provider = patch.object(HttpJsonReasoner, 'respond', side_effect=AssertionError('Context preview/local mode must not call an HTTP provider'))
        self.provider = self.no_provider.start()
        self.addCleanup(self.no_provider.stop)

    def run_client(self, scenario):
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('context_review_harness.js')), scenario],
            env={**os.environ, 'JACE_TEST_API': f'http://127.0.0.1:{self.server.server_port}'},
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.provider.assert_not_called()
        self.assertEqual(self.engine.list_memories('alice', memory_scope='work'), [self.work])
        self.assertEqual(self.engine.list_memories('bob', memory_scope='home'), [self.bob])

    def test_real_selected_local_answer_never_calls_configured_provider_or_learns(self):
        self.run_client('real_selected_local')
        self.assertEqual(self.engine.list_memories('alice', memory_scope='home'), [self.saved])

    def test_real_expired_memory_rejects_review_without_resend(self):
        self.run_client('real_expired_memory_conflict')
        self.assertTrue(self.engine.memory.get_owned('alice', self.saved.memory_id).expires_at.startswith('2000-'))

    def test_real_wrong_owner_token_cannot_preview_private_context(self):
        self.run_client('real_wrong_owner')
        self.assertEqual(self.engine.list_memories('alice', memory_scope='home'), [self.saved])

    def test_real_changed_memory_rejects_review_without_resend(self):
        self.run_client('real_changed_memory_conflict')
        records = self.engine.list_memories('alice', memory_scope='home')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].content, 'I prefer a changed cleaning method')


if __name__ == '__main__':
    unittest.main()
