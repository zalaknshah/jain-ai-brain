"""Synthetic-only inventory protocol and privacy regressions; no real corpus."""
import copy
import io
import json
import sys
import unittest
from unittest.mock import patch

from jace import cli
from jace import private_study as ss
from test_private_study import SyntheticBundle, canonical_bytes


class InventoryTests(unittest.TestCase):
    def test_inventory_counts_every_record_and_preserves_search_exclusions(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            result = session.inventory()
            self.assertEqual(result['status'], 'inventory')
            self.assertEqual(result['totals'], {'records': 107, 'search_eligible': 100, 'search_excluded': 7})
            self.assertEqual(result['by_category']['commentary'],
                             {'records': 103, 'search_eligible': 100, 'search_excluded': 3})
            self.assertEqual(result['by_category']['root_text']['records'], 0)
            self.assertEqual(result['by_category']['editorial_note']['search_excluded'], 1)
            self.assertEqual(result['by_chapter']['5'],
                             {'records': 12, 'search_eligible': 10, 'search_excluded': 2})
            for groups in (result['by_category'], result['by_chapter']):
                for key, total in result['totals'].items():
                    self.assertEqual(sum(group[key] for group in groups.values()), total)
                for group in groups.values():
                    self.assertEqual(group['records'], group['search_eligible'] + group['search_excluded'])
            self.assertEqual(result['totals']['search_eligible'], len(session._index.records))

    def test_review_flag_counts_are_overlapping_not_a_partition(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            # Synthetic internal metadata only, to exercise overlapping flags.
            session._records['NOTE'].update(citation_status='source_identifier_incomplete',
                within_quotation_markup=True, quotation_context_review_required=True)
            result = session.inventory()
            self.assertEqual(result['review_flags'], {'incomplete_source_identifier': 2,
                'quotation_context_review_required': 3, 'editorial_note': 1})
            self.assertTrue(result['review_flag_counts_may_overlap'])
            self.assertIn('do not enumerate every reason', result['reason'])
            self.assertEqual(result['totals']['search_excluded'], 7)

    def test_inventory_contains_no_passages_identities_or_source_paths(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            result = session.inventory()
            self.assertFalse(result['record_content_included'])
            self.assertNotIn('results', result)
            encoded = json.dumps(result)
            for record in bundle.records:
                for key in ('id', 'source_xml_path', 'text', 'source_uri'):
                    self.assertNotIn(record[key], encoded)
            self.assertNotIn(str(bundle.path), encoded)

    def test_arbitrary_metadata_does_not_become_output_keys_or_leak_values(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            session._records['S1_0'].update(category='private-category-sentinel', chapter=None)
            session._records['S1_1'].update(category=['invalid-category'], chapter='private-chapter-sentinel')
            session._records['S1_2']['chapter'] = 1
            session._records['S1_3']['chapter'] = '01'
            result = session.inventory()
            self.assertEqual(result['by_category']['unrecognized']['records'], 2)
            self.assertEqual(result['by_chapter']['unassigned']['records'], 1)
            self.assertEqual(result['by_chapter']['unrecognized']['records'], 3)
            self.assertNotIn('private-category-sentinel', json.dumps(result))
            self.assertNotIn('private-chapter-sentinel', json.dumps(result))

    def test_notices_fingerprints_and_non_admission_remain_visible(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            result = session.inventory()
            self.assertEqual(result['attribution'], bundle.attr.decode())
            self.assertEqual(result['preparation_changes'], bundle.changes.decode())
            self.assertEqual(result['fingerprints'], ss.source_fingerprints())
            self.assertEqual(result['warning'], ss.WARNING)
            self.assertEqual(result['admission_counts'], {flag: 0 for flag in ss.ADMISSION_FLAGS})
            for flag in ('query_persisted', 'provider_called', 'actions_executed',
                         'canonical_promoted', 'model_loaded', 'learned_ranking'):
                self.assertIs(result[flag], False)

    def test_counts_are_copies_and_inventory_does_not_mutate_record_or_index_state(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            records = copy.deepcopy(session._records)
            index_ids = [r['id'] for r in session._index.records]
            baseline = session.inventory()
            changed = session.inventory()
            changed['by_chapter']['1']['search_eligible'] = 999
            changed['admission_counts']['runtime_admitted'] = 107
            self.assertEqual(session.inventory(), baseline)
            self.assertEqual(session._records, records)
            self.assertEqual([r['id'] for r in session._index.records], index_ids)
            self.assertEqual(session.lookup('NOTE')['results'][0]['category'], 'editorial_note')

    def test_revocation_blocks_inventory(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            session.revoke()
            with self.assertRaises(ss.StudyError):
                session.inventory()

    def test_inventory_never_ranks_or_presents_records(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            with patch.object(session, '_present', side_effect=AssertionError('No passages')), \
                    patch.object(session._index, 'candidate_features', side_effect=AssertionError('No ranking')), \
                    patch.object(ss, 'read_regular', side_effect=AssertionError('No repeated IO')):
                self.assertEqual(session.inventory()['totals']['records'], 107)


class InventoryProtocolTests(unittest.TestCase):
    def test_exact_operation_dispatch_and_session_close(self):
        with SyntheticBundle() as bundle:
            with patch.object(ss.StudySession, 'revoke', autospec=True,
                              side_effect=ss.StudySession.revoke) as revoke:
                result = json.loads(ss.run_request(b'{"operation":"inventory"}',
                    consent=ss.consent_for_approved_source(), source_path=bundle.path/'source.xml', prepared_path=bundle.path))
                self.assertEqual(result['totals']['records'], 107)
                revoke.assert_called_once()
                self.assertFalse(revoke.call_args.args[0]._active)

    def test_extra_fields_and_malformed_protocol_are_rejected_before_io(self):
        invalid = [canonical_bytes({'operation': 'inventory', key: value})
                   for key, value in [('query', 'private query'), ('chapter', '1'), ('limit', 1),
                                      ('path', '/private/path'), ('save', True), ('training', True),
                                      ('category', None), ('offset', 0)]]
        invalid += [b'{"operation":"inventory","operation":"lookup"}',
                    b'{"operation":"Inventory"}', b'[]', b'{"operation":true}']
        for raw in invalid:
            with self.subTest(raw=raw), patch.object(ss, '_pinned') as read:
                with self.assertRaises(ss.StudyError):
                    ss.run_request(raw, consent=ss.consent_for_approved_source(),
                                   source_path='/not-read', prepared_path='/not-read')
                read.assert_not_called()

    def test_inventory_requires_explicit_consent_before_io(self):
        with patch.object(ss, '_pinned') as read, self.assertRaisesRegex(ss.StudyError, 'per-session opt-in'):
            ss.run_request(b'{"operation":"inventory"}', consent=None,
                           source_path='/not-read', prepared_path='/not-read')
        read.assert_not_called()

    def test_changed_source_remains_rejected_for_metadata_only_request(self):
        with SyntheticBundle() as bundle:
            (bundle.path/'source.xml').write_bytes(b'Changed synthetic bytes')
            with self.assertRaisesRegex(ss.StudyError, 'Fingerprint mismatch'):
                ss.run_request(b'{"operation":"inventory"}', consent=ss.consent_for_approved_source(),
                               source_path=bundle.path/'source.xml', prepared_path=bundle.path)

    def test_output_limit_still_revokes_without_returning_partial_inventory(self):
        with SyntheticBundle() as bundle, patch.object(ss, 'MAX_OUTPUT_BYTES', 1):
            with patch.object(ss.StudySession, 'revoke', autospec=True,
                              side_effect=ss.StudySession.revoke) as revoke:
                with self.assertRaisesRegex(ss.StudyError, 'output limit'):
                    ss.run_request(b'{"operation":"inventory"}', consent=ss.consent_for_approved_source(),
                                   source_path=bundle.path/'source.xml', prepared_path=bundle.path)
                revoke.assert_called_once()
                self.assertFalse(revoke.call_args.args[0]._active)

    def test_cli_inventory_uses_existing_pre_engine_path(self):
        with SyntheticBundle() as bundle:
            argv = ['jace', 'source-study', '--stdin', '--source-file', str(bundle.path/'source.xml'),
                    '--prepared-dir', str(bundle.path), '--opt-in-source', ss.SOURCE_SHA256,
                    '--opt-in-records', ss.RECORDS_SHA256, '--accept-license', ss.LICENSE]
            stdin = io.TextIOWrapper(io.BytesIO(b'{"operation":"inventory"}'), encoding='utf-8')
            with patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', stdin), \
                    patch.object(sys, 'stdout', io.StringIO()) as out, \
                    patch.object(cli, 'CognitiveEngine', side_effect=AssertionError('No engine')) as engine:
                cli.main()
                self.assertEqual(json.loads(out.getvalue())['status'], 'inventory')
                engine.assert_not_called()


if __name__ == '__main__':
    unittest.main()
