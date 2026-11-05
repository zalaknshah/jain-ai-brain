"""Synthetic private-source fixtures only; no network, engine or corpus package."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jace import private_study as ss
from jace import cli


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def sample_record(identity, chapter, text, *, category='commentary', incomplete=False, ancestor=False, inline=False):
    return {'id': identity, 'source_xml_id': identity, 'chapter': str(chapter), 'text': text,
            'text_sha256': ss.sha256(text.encode()), 'source_sha256': ss.SOURCE_SHA256,
            'source_xml_path': '/TEI[1]/text[1]/body[1]/p[' + identity + ']',
            'source_uri': 'https://example.invalid/synthetic-fixture', 'source_text_parts': [
                {'position': 1, 'text': text, 'xml_path': '/synthetic/text()'}],
            'category': category, 'license': ss.LICENSE, 'attribution_file': 'ATTRIBUTION.md',
            'source_note_targets': ['#ROOT_1'] if category == 'editorial_note' else [],
            'source_note_xml_paths': ['/synthetic/note[1]'] if category == 'editorial_note' else [],
            'source_responsibility': None, 'source_declared_language': 'sa-Latn',
            'language_review_status': 'not_reviewed', 'target_chapters': [],
            'citation_status': 'source_identifier_incomplete' if incomplete else 'source_identifier_present_unreviewed',
            'within_quotation_markup': ancestor, 'contains_quotation_markup': inline,
            'quotation_context_review_required': ancestor or inline,
            'quotation_xml_paths': ['/synthetic/q[1]'] if inline else [],
            **{flag: False for flag in ss.ADMISSION_FLAGS}}


class SyntheticBundle:
    """Only synthetic fixtures; never open approved real inputs in these unit tests."""
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='source-study-tests-')
        self.path = Path(self.temp.name)
        self.source = b'<TEI><text>Synthetic fixture only</text></TEI>'
        self.source_hash = ss.sha256(self.source)
        self.blob = hashlib.sha1(b'blob ' + str(len(self.source)).encode() + b'\0' + self.source).hexdigest()
        self.records = []
        for chapter in range(1, 11):
            for number in range(10):
                # Fixed synthetic alphabetic suffixes make every fragment distinct without digits.
                suffix = chr(97 + chapter) + chr(97 + number)
                text = f'§ {chapter * 100 + number}. pramāṇa{suffix} darśana{suffix} caritra{suffix} mokṣamārga{suffix} anekānta{suffix} saṃvara{suffix}'
                record = sample_record(f'S{chapter}_{number}', chapter, text)
                record['source_sha256'] = self.source_hash
                self.records.append(record)
        for record in [sample_record('INCOMPLETE', 5, 'akṣara lekhana', incomplete=True),
                       sample_record('ANCESTOR', 5, 'quoted source passage', ancestor=True),
                       sample_record('INLINE', 6, 'inline quotation passage', inline=True),
                       sample_record('NOTE', 7, 'for x read y; note only', category='editorial_note'),
                       sample_record('META', 7, 'modern metadata', category='edition_metadata'),
                       sample_record('PARATEXT', 7, 'a heading', category='paratext'),
                       sample_record('QUOTE', 7, 'isolated quotation', category='quotation_fragment')]:
            record['source_sha256'] = self.source_hash
            self.records.append(record)
        self.attr = b'Fixture attribution and CC BY-SA 4.0 license notice\n'
        self.changes = b'Fixture original preparation change notice\n'
        self.records_raw = b''.join(canonical_bytes(r).replace(b'\n', b'') + b'\n' for r in self.records)
        self.manifest = {'source_sha256': self.source_hash, 'records_sha256': ss.sha256(self.records_raw),
                         'attribution_sha256': ss.sha256(self.attr), 'change_notice_sha256': ss.sha256(self.changes),
                         'source_git_blob_sha': self.blob, 'license': ss.LICENSE}
        self.manifest_raw = canonical_bytes(self.manifest)
        for name, data in [('source.xml', self.source), ('records.jsonl', self.records_raw),
                           ('ATTRIBUTION.md', self.attr), ('CHANGES.md', self.changes),
                           ('manifest.json', self.manifest_raw)]:
            (self.path / name).write_bytes(data)
        self.patch = patch.multiple(ss, SOURCE_SHA256=self.source_hash, SOURCE_GIT_BLOB=self.blob,
                                    RECORDS_SHA256=ss.sha256(self.records_raw), MANIFEST_SHA256=ss.sha256(self.manifest_raw),
                                    ATTRIBUTION_SHA256=ss.sha256(self.attr), CHANGES_SHA256=ss.sha256(self.changes))
        self.patch.start()
        return self

    def __exit__(self, *args):
        self.patch.stop()
        self.temp.cleanup()

    def open(self):
        return ss.StudySession(ss.consent_for_approved_source(), source_path=self.path / 'source.xml', prepared_path=self.path)


class ConsentTests(unittest.TestCase):
    def test_default_denial_precedes_io(self):
        with patch.object(ss, '_pinned') as io:
            with self.assertRaisesRegex(ss.StudyError, 'Explicit per-session opt-in'):
                ss.StudySession(source_path='/synthetic/private/source.xml', prepared_path='/synthetic/private/prepared')
            io.assert_not_called()

    def test_bound_consent_denies_each_wrong_field(self):
        good = ss.consent_for_approved_source().__dict__
        for key, value in [('source_sha256', '0' * 64), ('records_sha256', '0' * 64),
                           ('accepted_license', 'proprietary'), ('purpose', 'canonical-training'),
                           ('opted_in', False), ('opted_in', 1)]:
            with self.subTest(key=key, value=value), patch.object(ss, '_pinned') as io:
                with self.assertRaisesRegex(ss.StudyError, 'Explicit per-session opt-in'):
                    ss.StudySession(ss.Consent(**{**good, key: value}),
                                    source_path='/synthetic/private/source.xml', prepared_path='/synthetic/private/prepared')
                io.assert_not_called()

    def test_revoke_is_terminal_and_releases_session_references(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            session.revoke()
            session.revoke()
            for operation in [lambda: session.lookup('S1_0'),
                              lambda: session.search('pramāṇa darśana', query_language='sa-Latn')]:
                with self.assertRaises(ss.StudyError):
                    operation()
            self.assertEqual(session._bytes, {})
            self.assertIsNone(session._index)

    def test_context_manager_revokes(self):
        with SyntheticBundle() as bundle:
            with bundle.open() as session:
                self.assertEqual(session.lookup('S1_0')['status'], 'found')
            with self.assertRaises(ss.StudyError):
                session.lookup('S1_0')


class IntegrityTests(unittest.TestCase):
    def test_every_pinned_input_tamper_is_rejected(self):
        for name in ['source.xml', 'records.jsonl', 'manifest.json', 'ATTRIBUTION.md', 'CHANGES.md']:
            with self.subTest(name=name), SyntheticBundle() as bundle:
                target = bundle.path / name
                target.write_bytes(target.read_bytes() + b' ')
                with self.assertRaises(ss.StudyError):
                    bundle.open()

    def test_same_verified_bytes_used_after_source_mutation(self):
        with SyntheticBundle() as bundle:
            with patch.object(ss, 'read_regular', wraps=ss.read_regular) as reader:
                session = bundle.open()
                self.assertEqual(reader.call_count, 5)
                original = session.lookup('S1_0')['results'][0]['text']
                (bundle.path / 'records.jsonl').write_text('tampered')
                self.assertEqual(session.lookup('S1_0')['results'][0]['text'], original)
                self.assertEqual(reader.call_count, 5)
                with self.assertRaises(ss.StudyError):
                    bundle.open()

    def test_no_canonical_promotion_and_no_mutable_record_escape(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            result = session.lookup('S1_0')['results'][0]
            self.assertTrue(all(result[flag] is False for flag in ss.ADMISSION_FLAGS))
            result['training_admitted'] = True
            result['source_text_parts'][0]['text'] = 'modified'
            fresh = session.lookup('S1_0')['results'][0]
            self.assertFalse(fresh['training_admitted'])
            self.assertNotEqual(fresh['source_text_parts'][0]['text'], 'modified')
            self.assertEqual((bundle.path / 'records.jsonl').read_bytes(), bundle.records_raw)

    def test_record_validation_rejects_promoted_flags_or_text_changes(self):
        with SyntheticBundle() as bundle:
            for key, value in [('training_admitted', True), ('scholarly_verified', True),
                               ('runtime_admitted', True), ('text', 'silent rewrite'),
                               ('quotation_context_review_required', True)]:
                record = copy.deepcopy(bundle.records[0])
                record[key] = value
                with self.subTest(key=key), self.assertRaises(ss.StudyError):
                    ss._validate_records(canonical_bytes(record))

    def test_secure_io_rejects_final_and_ancestor_symlinks(self):
        with SyntheticBundle() as bundle:
            target = bundle.path / 'source.xml'
            link = bundle.path / 'link.xml'
            link.symlink_to(target)
            with self.assertRaises(ss.StudyError):
                ss.read_regular(link, 4096)
            directory = bundle.path / 'link-directory'
            directory.symlink_to(bundle.path, target_is_directory=True)
            with self.assertRaises(ss.StudyError):
                ss.read_regular(directory / 'source.xml', 4096)

    def test_secure_io_rejects_nonregular_large_and_relative(self):
        with SyntheticBundle() as bundle:
            for path, cap in [(bundle.path, 4096), (bundle.path / 'source.xml', 1), (Path('relative'), 4096)]:
                with self.subTest(path=str(path)), self.assertRaises(ss.StudyError):
                    ss.read_regular(path, cap)
            fifo = bundle.path / 'fifo'
            os.mkfifo(fifo)
            with self.assertRaises(ss.StudyError):
                ss.read_regular(fifo, 4096)

    def test_missing_input_fails_closed(self):
        with SyntheticBundle() as bundle:
            (bundle.path / 'ATTRIBUTION.md').unlink()
            with self.assertRaises(ss.StudyError):
                bundle.open()


class RetrievalTests(unittest.TestCase):
    def test_exclusions_are_absent_from_default_index_but_preserved_in_lookup(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            self.assertEqual(len(session._index.records), 100)
            for identity in ['INCOMPLETE', 'ANCESTOR', 'INLINE', 'NOTE', 'META', 'PARATEXT', 'QUOTE']:
                response = session.lookup(identity)
                result = response['results'][0]
                self.assertIn('EXCLUDED', ' '.join(result['warnings']))
                original = next(r for r in bundle.records if r['id'] == identity)
                for key, value in original.items():
                    self.assertEqual(result[key], value)
                self.assertEqual(response['attribution'], bundle.attr.decode())
            self.assertIn('INCOMPLETE SOURCE IDENTIFIER', ' '.join(session.lookup('INCOMPLETE')['results'][0]['warnings']))
            for identity in ['ANCESTOR', 'INLINE']:
                self.assertIn('QUOTATION CONTEXT', ' '.join(session.lookup(identity)['results'][0]['warnings']))
            self.assertIn('EDITORIAL NOTE', ' '.join(session.lookup('NOTE')['results'][0]['warnings']))
            self.assertEqual(session.lookup('NOTE')['results'][0]['source_note_targets'], ['#ROOT_1'])

    def test_lookup_structural_path_and_missing_id(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            path = bundle.records[0]['source_xml_path']
            self.assertEqual(session.lookup(path)['results'][0]['id'], 'S1_0')
            self.assertEqual(session.lookup('not-present')['status'], 'not_found')

    def test_unrelated_or_unsupported_queries_abstain(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            cases = [('what should my business do', 'en'), ('मेरा काम', 'hi'), ('મારું કામ', 'gu'),
                     ('pramāṇaba darśanaba', None), ('मेरा काम', 'sa-Latn'),
                     ('quantum pineapple refrigerator', 'sa-Latn'), ('pramāṇaba', 'sa-Latn')]
            for query, language in cases:
                with self.subTest(query=query):
                    response = session.search(query, query_language=language)
                    self.assertEqual(response['status'], 'abstained')
                    self.assertEqual(response['results'], [])

    def test_literal_search_returns_original_excerpts_and_all_flags(self):
        with SyntheticBundle() as bundle:
            session = bundle.open()
            record = bundle.records[0]
            query = ' '.join(ss.tokens(record['text'])[0:4])
            result = session.search(query, query_language='sa-Latn')
            self.assertEqual(result['status'], 'matches')
            first = result['results'][0]
            self.assertEqual(first['id'], record['id'])
            self.assertEqual(first['text'], record['text'])
            self.assertTrue(all(first[f] is False for f in ss.ADMISSION_FLAGS))
            self.assertFalse(result['query_persisted'])
            self.assertNotIn('query', session.__dict__)


class StdinProtocolTests(unittest.TestCase):
    def test_valid_lookup_and_search_return_notices_and_no_mutations(self):
        with SyntheticBundle() as b:
            for request in [dict(operation='lookup', id='S1_0'),
                            dict(operation='search', query='pramāṇaba darśanaba', query_language='sa-Latn')]:
                result = json.loads(ss.run_request(canonical_bytes(request),
                    consent=ss.consent_for_approved_source(), source_path=b.path/'source.xml', prepared_path=b.path))
                self.assertIn(result['status'], ('found', 'matches'))
                self.assertEqual(result['license'], ss.LICENSE)
                for flag in ('query_persisted', 'provider_called', 'actions_executed',
                             'canonical_promoted', 'model_loaded', 'learned_ranking'):
                    self.assertIs(result[flag], False)

    def test_invalid_protocol_never_opens_source(self):
        requests = [b'', b' ' * 4097, b'[]', b'null', b'{', b'{"operation":"lookup","operation":"search"}',
                    b'[' * 1100 + b']' * 1100,
                    canonical_bytes({'operation':'train'}),
                    canonical_bytes({'operation':'lookup','id':'x','learn':True}),
                    canonical_bytes({'operation':'lookup','id':''}),
                    canonical_bytes({'operation':'search','query':'a b','query_language':'sa-Latn','ranking':'learned'})]
        for bad in (True, 0, 21, 10**400, -10**400, None, '5', []):
            requests.append(canonical_bytes({'operation':'search','query':'a b','query_language':'sa-Latn','limit':bad}))
        for raw in requests:
            with self.subTest(raw=raw[:50]), patch.object(ss, '_pinned') as read:
                with self.assertRaises(ss.StudyError):
                    ss.run_request(raw, consent=ss.consent_for_approved_source(),
                                   source_path='/no-read.xml', prepared_path='/no-read')
                read.assert_not_called()

    def test_output_budget_revokes_session_and_emits_no_partial_result(self):
        with SyntheticBundle() as b, patch.object(ss, 'MAX_OUTPUT_BYTES', 1):
            with self.assertRaisesRegex(ss.StudyError, 'output limit'):
                ss.run_request(canonical_bytes({'operation':'lookup','id':'S1_0'}),
                    consent=ss.consent_for_approved_source(), source_path=b.path/'source.xml', prepared_path=b.path)

    def test_explicit_paths_and_unsupported_platform_fail_closed(self):
        for source, prepared in [(None,None), ('relative','/absolute'), ('/absolute','../relative')]:
            with self.subTest(source=source), patch.object(ss, '_pinned') as read:
                with self.assertRaises(ss.StudyError):
                    ss.StudySession(ss.consent_for_approved_source(), source_path=source, prepared_path=prepared)
                read.assert_not_called()
        with patch.object(ss.os, 'supports_dir_fd', set()):
            with self.assertRaisesRegex(ss.StudyError, 'requires POSIX'):
                ss.read_regular(Path('/nonexistent'), 100)
        with self.assertRaises(ss.StudyError):
            ss.read_regular(Path('/invalid\x00file'), 100)

    def test_cli_branch_never_constructs_engine_and_reads_bounded_stdin(self):
        with SyntheticBundle() as b:
            argv = ['jace','source-study','--stdin','--source-file',str(b.path/'source.xml'),
                    '--prepared-dir',str(b.path),'--opt-in-source',ss.SOURCE_SHA256,
                    '--opt-in-records',ss.RECORDS_SHA256,'--accept-license',ss.LICENSE]
            stdin = io.TextIOWrapper(io.BytesIO(canonical_bytes({'operation':'lookup','id':'S1_0'})), encoding='utf-8')
            with patch.object(sys,'argv',argv), patch.object(sys,'stdin',stdin), patch.object(sys,'stdout',io.StringIO()) as out, \
                    patch.object(cli,'CognitiveEngine',side_effect=AssertionError('engine must not initialize')) as engine:
                cli.main()
                result = json.loads(out.getvalue())
                self.assertEqual(result['status'], 'found')
                engine.assert_not_called()

    def test_cli_invalid_request_has_controlled_error_without_source_io(self):
        argv = ['jace','source-study','--stdin','--source-file','/missing', '--prepared-dir','/missing',
                '--opt-in-source',ss.SOURCE_SHA256,'--opt-in-records',ss.RECORDS_SHA256,'--accept-license',ss.LICENSE]
        stdin = io.TextIOWrapper(io.BytesIO(b'{"operation":"train"}'), encoding='utf-8')
        with patch.object(sys,'argv',argv), patch.object(sys,'stdin',stdin), patch.object(sys,'stderr',io.StringIO()) as err, \
                patch.object(ss,'_pinned') as read, self.assertRaises(SystemExit) as exited:
            cli.main()
        self.assertEqual(exited.exception.code,2)
        self.assertIn('Source-study denied',err.getvalue())
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()

