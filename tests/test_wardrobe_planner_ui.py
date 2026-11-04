import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

import test_api_authorization as api_fixture

INVENTORY = {
    'items': [{'label': 'Everyday shirts', 'category': 'tops', 'quantity': 5,
               'condition': 'ready', 'fit': 'fits', 'use': 'unused',
               'preserve': False, 'ownership': 'mine'}],
    'minimum_ready': {'tops': 2, 'bottoms': 0, 'outerwear': 0, 'footwear': 0, 'other': 0},
}


@unittest.skipUnless(shutil.which('node'), 'Node.js required for script fixtures')
class WardrobePlannerUITests(unittest.TestCase):
    def scenario(self, name):
        result = subprocess.run(['node', str(Path(__file__).with_name('wardrobe_planner_harness.js')), name],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_create_review_then_explicit_plan(self): self.scenario('create_review_plan')
    def test_edit_resets_consent_and_blocks_unsaved_plan(self): self.scenario('edit_and_consumed_consent')
    def test_added_removed_rows_are_explicit_and_bounded(self): self.scenario('add_remove_bounds')
    def test_explicit_paged_inventory_selection(self): self.scenario('explicit_paging_selection')
    def test_changed_destination_during_health_prevents_private_write(self): self.scenario('stale_health_boundary')
    def test_changed_identity_during_stream_ignores_private_body(self): self.scenario('stale_body_boundary')
    def test_uncertain_write_never_retried(self): self.scenario('uncertain_write_no_retry')
    def test_plan_revision_conflict_clears_selection(self): self.scenario('plan_conflict_no_retry')
    def test_invalid_fields_destinations_and_old_protocol_fail_closed(self): self.scenario('invalid_inputs_and_protocol')
    def test_duplicate_labels_and_total_quantity_rejected(self): self.scenario('duplicate_and_total_bounds')
    def test_mismatched_scope_revision_inventory_and_action_status_rejected(self): self.scenario('wrong_scope_and_actions')
    def test_all_decisions_and_overlapping_counts(self): self.scenario('mixed_inventory_all_decisions')
    def test_malformed_owned_memory_cursor_and_type_fail_closed(self): self.scenario('malformed_memory_and_cursor')
    def test_token_change_clears_private_draft(self): self.scenario('token_change_clears_private_draft')
    def test_mismatched_counts_and_surplus_rejected(self): self.scenario('mismatched_counts_and_surplus')
    def test_text_rendering_scope_and_page_exit_privacy_reset(self): self.scenario('text_render_and_privacy_reset')
    def test_streaming_response_cap(self): self.scenario('oversized_response')
    def test_late_plan_ignored_after_cancel(self): self.scenario('stale_plan_after_cancel')
    def test_mismatched_save_remains_uncertain_and_not_retried(self): self.scenario('mismatched_saved_record')
    def test_new_save_expiry_response_must_match_submitted_instant(self): self.scenario('new_save_expiry_binding')
    def test_expiry_normalization_preserves_exact_microseconds(self): self.scenario('exact_expiry_normalization')
    def test_invalid_expiry_rejected_before_any_request(self): self.scenario('invalid_expiry_before_write')
    def test_existing_inventory_expiry_remains_bound(self): self.scenario('existing_expiry_remains_bound')
    def test_multiple_inventories_need_explicit_selection(self): self.scenario('multiple_inventory_selection')
    def test_unicode_composition_does_not_rewrite_user_label(self): self.scenario('noncanonical_label_preserved')


@unittest.skipUnless(shutil.which('node'), 'Node.js required for actual loopback integration')
class WardrobePlannerLoopbackTests(unittest.TestCase):
    tearDown = api_fixture.ApiAuthorizationTests.tearDown

    def setUp(self):
        api_fixture.ApiAuthorizationTests.setUp(self)
        self.work = self.engine.remember('alice', 'Unrelated work fixture', memory_scope='work')[0]
        self.bob = self.engine.remember('bob', 'Unrelated Bob fixture', memory_scope='home')[0]
        def forbidden(*args):
            raise AssertionError('Dedicated wardrobe planner must never call a provider')
        self.engine.reasoner.respond = forbidden

    def run_client(self, name):
        result = subprocess.run(['node', str(Path(__file__).with_name('wardrobe_planner_harness.js')), name],
                                env={**os.environ, 'JACE_TEST_API': f'http://127.0.0.1:{self.server.server_port}'},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.engine.list_memories('alice', memory_scope='work'), [self.work])
        self.assertEqual(self.engine.list_memories('bob', memory_scope='home'), [self.bob])

    def saved_inventory(self):
        return self.engine.save_wardrobe_inventory('alice', INVENTORY, confirm_save=True, memory_scope='home')[0]

    def test_real_create_reload_update_plan_without_provider(self):
        self.run_client('real_create_edit_plan')
        records = self.engine.list_memories('alice', memory_scope='home')
        self.assertEqual(len(records), 1)
        item = json.loads(records[0].content)['inventory']['items'][0]
        self.assertEqual(item['quantity'], 6)
        self.assertIs(item['preserve'], True)

    def test_real_microsecond_offset_expiry_normalized_and_preserved(self):
        self.run_client('real_exact_expiry_normalization')
        records = self.engine.list_memories('alice', memory_scope='home')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].expires_at, '2027-01-01T00:00:00.123456+00:00')

    def test_real_conflict_before_plan_and_update(self):
        record = self.saved_inventory()
        self.run_client('real_conflict')
        value = json.loads(self.engine.memory.get_owned('alice', record.memory_id).content)
        self.assertEqual(value['inventory']['items'][0]['quantity'], 7)

    def test_real_expiration_and_wrong_owner_cannot_create(self):
        record = self.saved_inventory()
        self.run_client('real_expiry_and_isolation')
        self.assertEqual(len(self.engine.list_memories('alice', memory_scope='home')), 1)
        self.assertTrue(self.engine.memory.get_owned('alice', record.memory_id).expires_at.startswith('2000-'))


if __name__ == '__main__':
    unittest.main()
