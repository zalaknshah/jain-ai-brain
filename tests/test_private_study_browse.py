"""Synthetic-only tests for stateless, literal private-source browsing."""
import io
import json
import sys
import unittest
from unittest.mock import patch

from jace import cli
from jace import private_study as ss
from test_private_study import SyntheticBundle, canonical_bytes


class BrowseTests(unittest.TestCase):
    def test_all_pages_preserve_preparation_order_and_every_original_field(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            collected = []
            offset = 0
            while True:
                result = session.browse(offset=offset, limit=20)
                self.assertEqual(result['order'], 'prepared_record_order')
                self.assertEqual(result['total'], len(bundle.records))
                self.assertEqual(result['offset'], offset)
                self.assertLessEqual(len(result['results']), 20)
                collected.extend(result['results'])
                offset = result['next_offset']
                if offset is None:
                    break
            self.assertEqual([r['id'] for r in collected], [r['id'] for r in bundle.records])
            self.assertNotEqual([r['id'] for r in collected], sorted(r['id'] for r in bundle.records))
            for returned, original in zip(collected, bundle.records):
                for key, value in original.items():
                    self.assertEqual(returned[key], value)
                self.assertTrue(all(returned[flag] is False for flag in ss.ADMISSION_FLAGS))

    def test_filters_select_exact_recorded_chapter_and_category(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            for chapter, category in [('1', None), (None, 'editorial_note'),
                                      ('7', 'editorial_note'), ('6', 'commentary')]:
                expected = [r['id'] for r in bundle.records
                            if (chapter is None or r['chapter'] == chapter)
                            and (category is None or r['category'] == category)]
                result = session.browse(chapter=chapter, category=category, limit=20)
                self.assertEqual([r['id'] for r in result['results']], expected)
                self.assertEqual(result['total'], len(expected))
                self.assertEqual(result['filters'], {'chapter': chapter, 'category': category})

    def test_zero_matches_and_exact_end_are_complete_not_a_dropped_page(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            for result in [session.browse(category='root_text'), session.browse(offset=len(bundle.records))]:
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['results'], [])
                self.assertIsNone(result['next_offset'])
            with self.assertRaisesRegex(ss.StudyError, 'exceeds the number'):
                session.browse(offset=len(bundle.records) + 1)
            with self.assertRaisesRegex(ss.StudyError, 'exceeds the number'):
                session.browse(offset=2, category='editorial_note')

    def test_excluded_records_keep_all_warnings_and_notices(self):
        with SyntheticBundle() as bundle, bundle.open() as session:
            result = session.browse(offset=100, limit=20)
            self.assertEqual(result['attribution'], bundle.attr.decode())
            self.assertEqual(result['preparation_changes'], bundle.changes.decode())
            for item in result['results']:
                self.assertIn('EXCLUDED', ' '.join(item['warnings']))
                self.assertEqual(item, session.lookup(item['id'])['results'][0])
            self.assertEqual(len(session._index.records), 100)
            self.assertIn('not relevance or a doctrinal relationship', result['reason'])

    def test_repeated_pages_are_stable_across_sessions_without_server_state(self):
        with SyntheticBundle() as bundle:
            with bundle.open() as first:
                a = first.browse(offset=2, limit=3, chapter='1')
                self.assertEqual(a, first.browse(offset=2, limit=3, chapter='1'))
            with bundle.open() as second:
                self.assertEqual(a, second.browse(offset=2, limit=3, chapter='1'))

    def test_results_are_deep_copies_and_revocation_blocks_browse(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            result = session.browse()
            result['results'][0]['source_text_parts'][0]['text'] = 'changed'
            result['results'][0]['runtime_admitted'] = True
            self.assertNotEqual(session.browse()['results'][0]['source_text_parts'][0]['text'], 'changed')
            self.assertFalse(session.browse()['results'][0]['runtime_admitted'])
            session.revoke()
            with self.assertRaises(ss.StudyError):
                session.browse()

    def test_direct_method_rejects_invalid_bounds_and_filters(self):
        invalid = [{'offset': value} for value in (True, -1, 2001, 1.0, None, '1', [], 10**400)]
        invalid += [{'limit': value} for value in (True, 0, 21, 1.0, None, '1', [], 10**400)]
        invalid += [{'chapter': value} for value in ('0', '11', '01', ' 1', '', 1, True, [], {})]
        invalid += [{'category': value} for value in ('root', '', 'ROOT_TEXT', 1, True, [], {})]
        with SyntheticBundle() as bundle, bundle.open() as session:
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ss.StudyError):
                    session.browse(**options)


class BrowseProtocolTests(unittest.TestCase):
    def test_valid_protocol_defaults_and_pagination_preserve_no_action_flags(self):
        with SyntheticBundle() as bundle:
            for request in [{'operation': 'browse'},
                            {'operation': 'browse', 'offset': 2, 'limit': 3, 'chapter': '1', 'category': 'commentary'}]:
                result = json.loads(ss.run_request(canonical_bytes(request),
                    consent=ss.consent_for_approved_source(), source_path=bundle.path/'source.xml', prepared_path=bundle.path))
                self.assertEqual(result['status'], 'page')
                self.assertEqual(len(result['results']), request.get('limit', 5))
                self.assertEqual(result['next_offset'], request.get('offset', 0) + request.get('limit', 5))
                for flag in ('query_persisted', 'provider_called', 'actions_executed',
                             'canonical_promoted', 'model_loaded', 'learned_ranking'):
                    self.assertIs(result[flag], False)

    def test_invalid_protocol_rejected_before_source_io(self):
        bad_options = [{'offset': value} for value in (True, -1, 2001, None, '1', [], 10**400)]
        bad_options += [{'limit': value} for value in (True, 0, 21, None, '1', [], -10**400)]
        bad_options += [{'chapter': value} for value in (None, 1, '', '01', '11', [])]
        bad_options += [{'category': value} for value in (None, 'all', 'root', [], True)]
        bad_options += [{'query': 'a b'}, {'ranking': 'learned'}, {'save': True}, {'id': 'S1_0'}]
        for options in bad_options:
            with self.subTest(options=options), patch.object(ss, '_pinned') as read:
                with self.assertRaises(ss.StudyError):
                    ss.run_request(canonical_bytes({'operation': 'browse', **options}),
                        consent=ss.consent_for_approved_source(), source_path='/not-read', prepared_path='/not-read')
                read.assert_not_called()

    def test_browse_still_requires_per_invocation_consent_before_source_io(self):
        with patch.object(ss, '_pinned') as read, self.assertRaisesRegex(ss.StudyError, 'per-session opt-in'):
            ss.run_request(b'{"operation":"browse"}', consent=None,
                           source_path='/not-read', prepared_path='/not-read')
        read.assert_not_called()

    def test_output_limit_revokes_session_without_returning_partial_page(self):
        with SyntheticBundle() as bundle, patch.object(ss, 'MAX_OUTPUT_BYTES', 1):
            with patch.object(ss.StudySession, 'revoke', autospec=True, side_effect=ss.StudySession.revoke) as revoke:
                with self.assertRaisesRegex(ss.StudyError, 'output limit'):
                    ss.run_request(b'{"operation":"browse"}', consent=ss.consent_for_approved_source(),
                                   source_path=bundle.path/'source.xml', prepared_path=bundle.path)
                revoke.assert_called_once()
                self.assertFalse(revoke.call_args.args[0]._active)

    def test_cli_browse_uses_existing_pre_engine_path(self):
        with SyntheticBundle() as bundle:
            argv = ['jace', 'source-study', '--stdin', '--source-file', str(bundle.path/'source.xml'),
                    '--prepared-dir', str(bundle.path), '--opt-in-source', ss.SOURCE_SHA256,
                    '--opt-in-records', ss.RECORDS_SHA256, '--accept-license', ss.LICENSE]
            stdin = io.TextIOWrapper(io.BytesIO(b'{"operation":"browse","limit":2}'), encoding='utf-8')
            with patch.object(sys, 'argv', argv), patch.object(sys, 'stdin', stdin), \
                    patch.object(sys, 'stdout', io.StringIO()) as out, \
                    patch.object(cli, 'CognitiveEngine', side_effect=AssertionError('No engine')) as engine:
                cli.main()
                result = json.loads(out.getvalue())
                self.assertEqual([r['id'] for r in result['results']], ['S1_0', 'S1_1'])
                self.assertEqual(result['next_offset'], 2)
                engine.assert_not_called()


if __name__ == '__main__':
    unittest.main()
