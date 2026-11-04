"""Review/export regression tests use only original synthetic fixture text."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from jace import source_bundle as sb
from jace import source_review as sr
from jace.canonical import CanonicalStore

TEXT = '  Keep café 雪.\r\nSYNTHETIC_PRIVATE_MARKER never admit.\t\nFinal pending passage.  \n'
DATA = TEXT.encode('utf-8')
DIGEST = hashlib.sha256(DATA).hexdigest()
META = dict(work='Original fixture work', source='Synthetic authorship declaration', language='en',
            license_name='Synthetic rights declaration', location='Original fixture section',
            edition='Fixture edition', tags=['original', 'fixture'])
HTML = b'<!doctype html><title>Original synthetic review test document</title>'
ROOT = Path(__file__).resolve().parents[1]


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'original.txt'
        self.input.write_bytes(DATA)
        self.output = self.root / 'draft'
        self.report = self.root / 'decisions.json'
        self.exported = self.root / 'exported'

    def prepare(self, **changes):
        options = dict(META, confirm_copy=True, chunk_words=3, overlap_words=0)
        options.update(changes)
        with patch('jace.review_document.render_review_html', return_value=HTML):
            return sr.prepare_source_review([self.input], self.output, **options)

    def decisions(self, snapshot, choices=None):
        choices = choices or ['approve'] + ['pending'] * (len(snapshot['records']) - 1)
        return {'format': sr.DECISIONS_FORMAT, 'draft_revision': snapshot['draft_revision'],
                'reviewer': 'Original fixture reviewer',
                'decisions': [{'entry_id': item['entry']['entry_id'], 'record_revision': item['revision'],
                               'decision': choice, 'note': '' if choice == 'pending' else 'Original fixture decision rationale.'}
                              for item, choice in zip(snapshot['records'], choices)]}

    def save_report(self, value):
        self.report.write_text(json.dumps(value, ensure_ascii=True), encoding='utf-8')

    def reviewed(self, choices=None):
        manifest = self.prepare()
        snapshot = sr.load_review_package(manifest)
        self.save_report(self.decisions(snapshot, choices))
        return manifest, snapshot

    def export(self, manifest, **changes):
        options = dict(confirm_export=True, declare_qualified_review=True,
                       declare_rights_for_local_retrieval=True)
        options.update(changes)
        return sr.export_reviewed_sources(manifest, self.report, self.exported, **options)

    def assert_no_stage(self):
        self.assertEqual(list(self.root.glob('.jace-source-*')), [])

    def test_draft_is_private_complete_and_runtime_rejects_it(self):
        manifest = self.prepare()
        snapshot = sr.load_review_package(manifest)
        self.assertEqual(set(snapshot), {'protocol', 'kind', 'draft_revision', 'sources', 'records', 'limits'})
        self.assertEqual(snapshot['protocol'], 1)
        self.assertEqual(snapshot['kind'], 'review_only')
        self.assertEqual(snapshot['sources'], [{'sha256': DIGEST, 'byte_length': len(DATA)}])
        self.assertNotIn(str(self.root), json.dumps(snapshot))
        self.assertEqual((self.output / 'sources' / (DIGEST + '.txt')).read_bytes(), DATA)
        self.assertEqual((self.output / 'review.html').read_bytes(), HTML)
        self.assertTrue(all(item['entry']['verified'] is False for item in snapshot['records']))
        for reader in (sb.load_source_bundle, sb.load_corpus_records, CanonicalStore):
            with self.subTest(reader=reader), self.assertRaises(ValueError):
                reader(manifest)
        for path in (self.output, self.output / 'sources'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        for path in (manifest, self.output / 'review.html', self.output / 'sources' / (DIGEST + '.txt')):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assert_no_stage()

    def test_exact_unicode_crlf_tabs_and_overlapping_bytes(self):
        snapshot = sr.load_review_package(self.prepare(chunk_words=5, overlap_words=2))
        first, second = [item['entry'] for item in snapshot['records'][:2]]
        self.assertIn('\r\n', first['principle'])
        self.assertGreater(first['source_byte_end'], second['source_byte_start'])
        for record in snapshot['records']:
            item = record['entry']
            self.assertEqual(item['principle'].encode('utf-8'), DATA[item['source_byte_start']:item['source_byte_end']])
        self.assertIn('café', first['principle'])
        self.assertIn('雪', first['principle'])
        self.assertTrue(any('\t\n' in item['entry']['principle'] for item in snapshot['records']))

    def test_prepare_requires_literal_consent_before_reads_or_iteration(self):
        for consent in (False, None, 0, 1, 'true', [], {}):
            with self.subTest(consent=consent), patch.object(sb, 'read_source_file') as reader:
                with self.assertRaises(ValueError):
                    self.prepare(confirm_copy=consent)
                reader.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assert_no_stage()

    def test_invalid_metadata_and_chunks_fail_before_reads(self):
        cases = [{'work': ''}, {'language': 'x' * 65}, {'source': '\x1b'}, {'license_name': ''},
                 {'edition': ''}, {'tags': ['same', 'same']}, {'location': None}, {'work': '\ud800'},
                 {'chunk_words': 0}, {'chunk_words': True}, {'overlap_words': 3}, {'overlap_words': -1}]
        for changes in cases:
            with self.subTest(changes=changes), patch.object(sb, 'read_source_file') as reader:
                with self.assertRaises(ValueError): self.prepare(**changes)
                reader.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_explicit_collection_extension_and_duplicate_sources(self):
        for paths in ([], str(self.input), self.input, [self.input] * (sb.MAX_SOURCES + 1)):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                sr.prepare_source_review(paths, self.output, **META, confirm_copy=True)
        alias = self.root / 'bad.pdf'; alias.write_bytes(DATA)
        with self.assertRaises(ValueError):
            sr.prepare_source_review([alias], self.output, **META, confirm_copy=True)
        duplicate = self.root / 'copy.txt'; duplicate.write_bytes(DATA)
        with self.assertRaises(ValueError):
            sr.prepare_source_review([self.input, duplicate], self.output, **META, confirm_copy=True)
        self.assertFalse(self.output.exists())

    def test_export_subset_filters_records_not_whole_original_bytes(self):
        manifest, snapshot = self.reviewed(['approve', 'reject', 'pending'])
        result = self.export(manifest)
        loaded = sb.load_source_bundle(result['manifest_path'])
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0], {**snapshot['records'][0]['entry'], 'verified': True})
        self.assertNotIn('SYNTHETIC_PRIVATE_MARKER', json.dumps(loaded))
        backing = self.exported / 'sources' / (DIGEST + '.txt')
        self.assertIn(b'SYNTHETIC_PRIVATE_MARKER', backing.read_bytes())
        self.assertEqual(backing.read_bytes(), DATA)
        self.assertTrue(CanonicalStore(result['manifest_path']).source_bound)
        self.assertEqual((result['approved_records'], result['rejected_records'], result['pending_records'], result['source_count']), (1, 1, 1, 1))
        self.assertIn('WHOLE', result['warning'])
        self.assertIn('NOT filtered', result['warning'])
        runtime_raw = Path(result['manifest_path']).read_text()
        self.assertNotIn('reviewer', runtime_raw)
        self.assertNotIn('decision rationale', runtime_raw)
        self.assertFalse((self.exported / 'review.html').exists())
        for path in (self.exported, self.exported / 'sources'):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        for path in (backing, Path(result['manifest_path'])):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_only_approved_sources_retained(self):
        extra = self.root / 'other.md'; extra.write_text('Another original synthetic fixture.', encoding='utf-8')
        with patch('jace.review_document.render_review_html', return_value=HTML):
            manifest = sr.prepare_source_review([self.input, extra], self.output, **META, confirm_copy=True,
                                                chunk_words=3, overlap_words=0)
        snapshot = sr.load_review_package(manifest)
        self.save_report(self.decisions(snapshot))
        result = self.export(manifest)
        self.assertEqual(result['source_count'], 1)
        self.assertEqual([p.name for p in (self.exported / 'sources').iterdir()], [DIGEST + '.txt'])

    def test_export_requires_all_literal_declarations_before_reads(self):
        for field in ('confirm_export', 'declare_qualified_review', 'declare_rights_for_local_retrieval'):
            for value in (False, 1, None, 'true'):
                with self.subTest(field=field, value=value), patch.object(sr, '_read_review_snapshot') as read:
                    with self.assertRaisesRegex(ValueError, 'WHOLE'):
                        self.export(self.output / 'nonexistent.json', **{field: value})
                    read.assert_not_called()
        self.assertFalse(self.exported.exists())

    def test_at_least_one_approval_required(self):
        manifest, snapshot = self.reviewed(['reject', 'pending', 'reject'])
        with self.assertRaisesRegex(ValueError, 'at least one'): self.export(manifest)
        self.assertFalse(self.exported.exists())

    def test_decision_fields_cardinality_ids_and_revisions(self):
        manifest, snapshot = self.reviewed()
        original = self.decisions(snapshot)
        bad = []
        for key in original:
            value = copy.deepcopy(original); del value[key]; bad.append(value)
        for key, replacement in [('format', sb.FORMAT), ('draft_revision', 'a' * 64), ('reviewer', ''),
                                  ('decisions', {}), ('extra', 'unknown')]:
            value = copy.deepcopy(original); value[key] = replacement; bad.append(value)
        for replacement in ([], original['decisions'][:-1], original['decisions'] + original['decisions'][:1],
                            [original['decisions'][0]] * len(original['decisions'])):
            value = copy.deepcopy(original); value['decisions'] = replacement; bad.append(value)
        for key in original['decisions'][0]:
            value = copy.deepcopy(original); del value['decisions'][0][key]; bad.append(value)
        for key, replacement in [('entry_id', 'unknown'), ('entry_id', []), ('record_revision', 'b' * 64),
                                 ('record_revision', True), ('decision', 'approved'), ('decision', []),
                                 ('note', ''), ('note', ' \t\n'), ('extra', False)]:
            value = copy.deepcopy(original); value['decisions'][0][key] = replacement; bad.append(value)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                sr._validate_decisions(value, snapshot)
        self.assertFalse(self.exported.exists())

    def test_decision_strings_are_bounded_and_controls_rejected(self):
        _, snapshot = self.reviewed()
        for field, limit in [('reviewer', 128), ('note', 2000)]:
            for text in ('x' * (limit + 1), '\x00', '\x1b', '\u202e', '\u2066', '\ud800', 'bad\rtext'):
                value = self.decisions(snapshot)
                if field == 'reviewer': value[field] = text
                else: value['decisions'][0][field] = text
                with self.subTest(field=field, text=text[:20]), self.assertRaises(ValueError):
                    sr._validate_decisions(value, snapshot)
        value = self.decisions(snapshot)
        value['reviewer'] = '雪' * 128
        value['decisions'][0]['note'] = 'é' * 2000
        value['decisions'][1]['note'] = ' \t\r\n'
        self.assertEqual(len(sr._validate_decisions(value, snapshot)), 3)
        value['decisions'][0]['note'] = 'Original\r\nreview\tnote.'
        self.assertEqual(len(sr._validate_decisions(value, snapshot)), 3)

    def test_metadata_changes_invalidate_approval(self):
        manifest, snapshot = self.reviewed()
        original = json.loads(manifest.read_text())
        for field, replacement in [('title', 'Changed title'), ('guidance', 'Changed guidance'),
                ('work', 'Changed work'), ('source', 'Changed source'), ('license', 'Changed license'),
                ('location', 'Changed location'), ('edition', 'Changed edition'), ('language', 'fr'),
                ('tags', ['new']), ('entry_id', 'new:entry'), ('work', ' Original fixture work '),
                ('verified', True)]:
            changed = copy.deepcopy(original); changed['records'][0][field] = replacement
            manifest.write_text(json.dumps(changed), encoding='utf-8')
            with self.subTest(field=field), self.assertRaises(ValueError): self.export(manifest)
        manifest.write_text(json.dumps(original), encoding='utf-8')
        self.assertEqual(sr.load_review_package(manifest), snapshot)
        self.assertFalse(self.exported.exists())

    def test_span_change_or_source_change_invalidates_approval(self):
        manifest, snapshot = self.reviewed()
        original = json.loads(manifest.read_text())
        changed = copy.deepcopy(original); changed['records'][0]['source_ref']['start'] = 0
        manifest.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'): self.export(manifest)
        manifest.write_text(json.dumps(original), encoding='utf-8')
        backing = self.output / 'sources' / (DIGEST + '.txt')
        backing.write_bytes(DATA.replace(b'Keep', b'Edit'))
        with self.assertRaisesRegex(ValueError, 'digest'): self.export(manifest)
        # Even if all digest references are recomputed, existing decisions are stale.
        new_digest = hashlib.sha256(backing.read_bytes()).hexdigest()
        backing.rename(backing.parent / (new_digest + '.txt'))
        original['sources'][0].update(sha256=new_digest, path=f'sources/{new_digest}.txt')
        for record in original['records']: record['source_ref']['sha256'] = new_digest
        manifest.write_text(json.dumps(original), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'): self.export(manifest)
        self.assertFalse(self.exported.exists())

    def test_serialization_whitespace_and_object_key_order_do_not_change_revision(self):
        manifest, snapshot = self.reviewed()
        raw = json.loads(manifest.read_text())
        manifest.write_text('\n ' + json.dumps(raw, sort_keys=False, separators=(',', ':')) + ' \n', encoding='utf-8')
        self.assertEqual(sr.load_review_package(manifest), snapshot)
        self.assertEqual(self.export(manifest)['approved_records'], 1)

    def test_reordered_records_change_draft_revision_and_missing_sources_rejected(self):
        manifest, _ = self.reviewed()
        raw = json.loads(manifest.read_text()); raw['records'].reverse()
        manifest.write_text(json.dumps(raw), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'): self.export(manifest)
        raw['sources'] = []; manifest.write_text(json.dumps(raw), encoding='utf-8')
        with self.assertRaises(ValueError): sr.load_review_package(manifest)

    def test_export_uses_immutable_validated_source_snapshot(self):
        manifest, _ = self.reviewed()
        original = sr._validate_decisions
        backing = self.output / 'sources' / (DIGEST + '.txt')
        def mutate(report, snapshot):
            choices = original(report, snapshot)
            backing.write_bytes(b'Changed original synthetic source after validation.')
            self.report.write_text('changed report after validation', encoding='utf-8')
            return choices
        with patch.object(sr, '_validate_decisions', side_effect=mutate):
            result = self.export(manifest)
        self.assertEqual((self.exported / 'sources' / (DIGEST + '.txt')).read_bytes(), DATA)
        self.assertEqual(sb.load_source_bundle(result['manifest_path'])[0]['principle'], 'Keep café 雪.')

    def test_decision_tamper_during_read_rejected(self):
        manifest, _ = self.reviewed()
        original = os.read; changed = False
        def mutate(fd, size):
            nonlocal changed
            raw = original(fd, size)
            if not changed and sr.DECISIONS_FORMAT.encode() in raw:
                changed = True
                with self.report.open('ab') as stream: stream.write(b' ')
            return raw
        with patch.object(sb.os, 'read', side_effect=mutate), self.assertRaises(ValueError):
            self.export(manifest)
        self.assertTrue(changed)
        self.assertFalse(self.exported.exists())

    def test_source_and_manifest_tamper_during_snapshot_rejected(self):
        manifest = self.prepare()
        for target in (manifest, self.output / 'sources' / (DIGEST + '.txt')):
            original = sb._validated_records
            def mutate(records, sources, **kwargs):
                result = original(records, sources, **kwargs)
                with target.open('ab') as stream: stream.write(b' ')
                return result
            before = target.read_bytes()
            with self.subTest(target=target), patch.object(sb, '_validated_records', side_effect=mutate), self.assertRaises(ValueError):
                sr.load_review_package(manifest)
            target.write_bytes(before)

    def test_draft_and_decision_json_strictness_and_limits(self):
        manifest, _ = self.reviewed()
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '[' * 33 + ']' * 33,
                    '\ufeff{}', '{broken', '"\\ud800"', 'x' * (sr.MAX_DECISIONS_BYTES + 1)):
            self.report.write_text(raw, encoding='utf-8')
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError): self.export(manifest)
        self.assertFalse(self.exported.exists())
        for name, maximum in [('MAX_MANIFEST_BYTES', 1), ('MAX_SOURCE_BYTES', len(DATA) - 1),
                              ('MAX_TOTAL_SOURCE_BYTES', len(DATA) - 1), ('MAX_RECORDS', 2),
                              ('MAX_SOURCES', 0), ('MAX_PASSAGE_BYTES', 1), ('MAX_PASSAGE_CHARS', 1)]:
            with self.subTest(limit=name), patch.object(sb, name, maximum), self.assertRaises(ValueError):
                sr.load_review_package(manifest)

    def test_prepare_limits_never_publish_partial_packages(self):
        for name, maximum in [('MAX_RECORDS', 2), ('MAX_TOTAL_SOURCE_BYTES', len(DATA) - 1),
                              ('MAX_MANIFEST_BYTES', 1), ('MAX_REVIEW_HTML_BYTES', 1)]:
            with self.subTest(limit=name), patch.object(sb, name, maximum), self.assertRaises(ValueError):
                self.prepare()
            self.assertFalse(self.output.exists()); self.assert_no_stage()

    def test_runtime_and_legacy_corpora_not_accepted_as_drafts(self):
        manifest, _ = self.reviewed()
        result = self.export(manifest)
        with self.assertRaises(ValueError): sr.load_review_package(result['manifest_path'])
        manifest.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError): sr.load_review_package(manifest)

    def test_review_load_rejects_unknown_fields_or_undeclared_assets(self):
        manifest = self.prepare()
        original = json.loads(manifest.read_text())
        for field in ('top', 'source', 'record', 'reference'):
            raw = copy.deepcopy(original)
            target = raw if field == 'top' else raw['sources'][0] if field == 'source' else raw['records'][0] if field == 'record' else raw['records'][0]['source_ref']
            target['unknown'] = False
            manifest.write_text(json.dumps(raw), encoding='utf-8')
            with self.subTest(field=field), self.assertRaises(ValueError): sr.load_review_package(manifest)
        manifest.write_text(json.dumps(original), encoding='utf-8')
        (self.output / 'sources' / 'undeclared.txt').write_bytes(b'Original extra fixture.')
        with self.assertRaises(ValueError): sr.load_review_package(manifest)

    def test_symlink_ancestors_source_manifest_and_decision_paths_rejected(self):
        manifest, _ = self.reviewed()
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        for path in (alias / 'draft' / 'bundle.json', self.output / '..' / 'draft' / 'bundle.json'):
            with self.subTest(path=path), self.assertRaises(ValueError): sr.load_review_package(path)
        for target in (manifest, self.output / 'sources' / (DIGEST + '.txt'), self.report):
            backup = self.root / 'backup'; target.rename(backup); target.symlink_to(backup)
            with self.subTest(target=target), self.assertRaises(ValueError): self.export(manifest)
            target.unlink(); backup.rename(target)
        linked_report = alias / 'decisions.json'
        with self.assertRaises(ValueError):
            sr.export_reviewed_sources(manifest, linked_report, self.exported,
                confirm_export=True, declare_qualified_review=True, declare_rights_for_local_retrieval=True)
        with self.assertRaises(ValueError):
            sr.prepare_source_review([alias / 'original.txt'], self.root / 'alias-draft', **META, confirm_copy=True)

    def test_hardlinks_and_fifos_rejected_without_hanging(self):
        manifest, _ = self.reviewed()
        for target in (manifest, self.output / 'sources' / (DIGEST + '.txt'), self.report):
            link = self.root / 'hardlink'; os.link(target, link)
            with self.subTest(target=target, kind='hardlink'), self.assertRaises(ValueError): self.export(manifest)
            link.unlink()
            backup = target.read_bytes(); target.unlink(); os.mkfifo(target)
            with self.subTest(target=target, kind='fifo'), self.assertRaises(ValueError): self.export(manifest)
            target.unlink(); target.write_bytes(backup)
        self.input.unlink(); os.mkfifo(self.input)
        with self.assertRaises(ValueError): self.prepare()

    def test_prepare_existing_destination_never_overwritten(self):
        for kind in ('directory', 'file', 'symlink'):
            if kind == 'directory': self.output.mkdir()
            elif kind == 'file': self.output.write_bytes(b'Original existing data.')
            else: self.output.symlink_to(self.root / 'missing')
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.prepare()
            if kind == 'directory': self.output.rmdir()
            elif kind == 'file':
                self.assertEqual(self.output.read_bytes(), b'Original existing data.'); self.output.unlink()
            else: self.assertTrue(self.output.is_symlink()); self.output.unlink()
            self.assert_no_stage()

    def test_atomic_prepare_publication_race_never_overwrites_target(self):
        original = sb._rename_noreplace
        def race(parent, stage, target):
            self.output.mkdir(); (self.output / 'keep').write_bytes(b'Concurrent original fixture.')
            return original(parent, stage, target)
        with patch.object(sb, '_rename_noreplace', side_effect=race), self.assertRaises(ValueError): self.prepare()
        self.assertEqual((self.output / 'keep').read_bytes(), b'Concurrent original fixture.')
        self.assert_no_stage()

    def test_export_never_overwrites_previous_output(self):
        manifest, _ = self.reviewed(); result = self.export(manifest)
        before = Path(result['manifest_path']).read_bytes()
        with self.assertRaises(ValueError): self.export(manifest)
        self.assertEqual(Path(result['manifest_path']).read_bytes(), before)
        self.assert_no_stage()

    def test_output_parent_symlink_or_missing_parent_rejected(self):
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        for target in (alias / 'new', self.root / 'missing' / 'new'):
            with self.subTest(target=target), patch('jace.review_document.render_review_html', return_value=HTML), self.assertRaises(ValueError):
                sr.prepare_source_review([self.input], target, **META, confirm_copy=True)
        self.assert_no_stage()

    def test_renderer_and_writer_failures_rollback_owned_stage(self):
        with patch('jace.review_document.render_review_html', side_effect=ValueError('renderer failure')), self.assertRaises(ValueError):
            sr.prepare_source_review([self.input], self.output, **META, confirm_copy=True)
        for operation in ('_write_private', '_rename_noreplace'):
            with self.subTest(operation=operation), patch.object(sb, operation, side_effect=OSError('injected failure')), self.assertRaises(ValueError): self.prepare()
            self.assertFalse(self.output.exists()); self.assert_no_stage()
        original = sb._write_private
        def fail_html(parent, name, data):
            original(parent, name, data)
            if name == 'review.html': raise OSError('injected after HTML write')
        with patch.object(sb, '_write_private', side_effect=fail_html), self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists()); self.assert_no_stage()

    def test_written_review_html_tampering_is_rejected_and_cleaned(self):
        original = sb._write_private
        def tamper(parent, name, data):
            return original(parent, name, data + b'changed' if name == 'review.html' else data)
        with patch.object(sb, '_write_private', side_effect=tamper), self.assertRaisesRegex(ValueError, 'review document changed'): self.prepare()
        self.assertFalse(self.output.exists()); self.assert_no_stage()

    def test_cleanup_failure_leaves_private_stage_and_never_claims_publication(self):
        original = sb._write_private
        def fail_html(parent, name, data):
            original(parent, name, data)
            if name == 'review.html': raise OSError('injected after HTML write')
        with patch.object(sb, '_write_private', side_effect=fail_html), patch.object(sb, '_remove_stage', side_effect=OSError('injected cleanup failure')), self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())
        stages = list(self.root.glob('.jace-source-*')); self.assertEqual(len(stages), 1)
        self.assertEqual(stat.S_IMODE(stages[0].stat().st_mode), 0o700)
        self.assertEqual((stages[0] / 'review.html').read_bytes(), HTML)

    def test_only_controlled_review_asset_supported_and_modes_never_guessed(self):
        manifest = self.prepare(); raw = json.loads(manifest.read_text())
        for options in ({'require_review': False}, {'review_html': HTML},
                        {'expected_format': sr.FORMAT, 'require_review': True, 'review_html': HTML},
                        {'expected_format': sr.FORMAT, 'require_review': False},
                        {'expected_format': 'unknown', 'require_review': False, 'review_html': HTML}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                sb._write_bundle(self.exported, {DIGEST: DATA}, raw['records'], **options)
        with self.assertRaises(TypeError):
            sb._write_bundle(self.exported, {DIGEST: DATA}, raw['records'], extra_files={'escape': b'x'})
        self.assertFalse(self.exported.exists())


class ReviewIntegrationTests(unittest.TestCase):
    def test_cli_warns_before_confirmed_export_call(self):
        spec = importlib.util.spec_from_file_location('review_sources_cli', ROOT / 'scripts/review_sources.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output = io.StringIO()
        def exporter(*args, **kwargs):
            self.assertIn('WHOLE', output.getvalue())
            self.assertIn('NOT filtered', output.getvalue())
            self.assertIn('rejected, pending or unreviewed', output.getvalue())
            self.assertTrue(all(value is True for value in kwargs.values()))
            return {'manifest_path': 'synthetic-output/bundle.json', 'approved_records': 1, 'source_count': 1}
        with redirect_stdout(output), patch.object(cli, 'export_reviewed_sources', side_effect=exporter) as call:
            self.assertEqual(cli.main(['export', '--manifest', 'synthetic-draft/bundle.json',
                '--decisions', 'synthetic-report.json', '--output', 'synthetic-output', '--confirm-export',
                '--declare-qualified-review', '--declare-rights-for-local-retrieval']), 0)
            call.assert_called_once()

    def test_real_renderer_integration_and_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'original.txt'; source.write_bytes(DATA)
            base = [sys.executable, str(ROOT / 'scripts/review_sources.py')]
            prepare = base + ['prepare', str(source), '--output', str(root / 'draft'), '--work', META['work'],
                '--source', META['source'], '--language', 'en', '--license', META['license_name'],
                '--location', META['location'], '--chunk-words', '3', '--overlap-words', '0']
            denied = subprocess.run(prepare, capture_output=True, text=True, timeout=10)
            self.assertEqual(denied.returncode, 0, denied.stderr)
            self.assertIn('No files were read or copied', denied.stdout)
            self.assertFalse((root / 'draft').exists())
            made = subprocess.run(prepare + ['--confirm-copy'], capture_output=True, text=True, timeout=10)
            self.assertEqual(made.returncode, 0, made.stderr)
            manifest = root / 'draft' / 'bundle.json'; snapshot = sr.load_review_package(manifest)
            html = (root / 'draft' / 'review.html').read_text(encoding='utf-8')
            self.assertIn('Content-Security-Policy', html)
            self.assertIn('WHOLE', html)
            report = {'format': sr.DECISIONS_FORMAT, 'draft_revision': snapshot['draft_revision'],
                'reviewer': 'Synthetic CLI reviewer', 'decisions': [
                    {'entry_id': record['entry']['entry_id'], 'record_revision': record['revision'],
                     'decision': 'approve' if index == 0 else 'pending', 'note': 'Original fixture review.' if index == 0 else ''}
                    for index, record in enumerate(snapshot['records'])]}
            report_path = root / 'decisions.json'; report_path.write_text(json.dumps(report), encoding='utf-8')
            export = base + ['export', '--manifest', str(manifest), '--decisions', str(report_path), '--output', str(root / 'runtime')]
            no_export = subprocess.run(export, capture_output=True, text=True, timeout=10)
            self.assertEqual(no_export.returncode, 0, no_export.stderr)
            self.assertIn('WHOLE', no_export.stdout); self.assertIn('NOT filtered', no_export.stdout)
            self.assertIn('No files were read or exported', no_export.stdout)
            self.assertFalse((root / 'runtime').exists())
            completed = subprocess.run(export + ['--confirm-export', '--declare-qualified-review', '--declare-rights-for-local-retrieval'],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(len(CanonicalStore(root / 'runtime' / 'bundle.json').all()), 1)
            self.assertEqual((root / 'runtime' / 'sources' / (DIGEST + '.txt')).read_bytes(), DATA)
            repeated = subprocess.run(export + ['--confirm-export', '--declare-qualified-review', '--declare-rights-for-local-retrieval'],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(repeated.returncode, 2)
            self.assertNotIn('Traceback', repeated.stderr)
            self.assertIn('not published', repeated.stderr)

    def test_cli_help_and_missing_flags_do_not_read_nonexistent_paths(self):
        base = [sys.executable, str(ROOT / 'scripts/review_sources.py')]
        help_result = subprocess.run(base + ['--help'], capture_output=True, text=True, timeout=5)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('cannot run', help_result.stdout)
        self.assertIn('No network', help_result.stdout)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'never-made'
            command = base + ['export', '--manifest', '/nonexistent/draft.json', '--decisions', '/nonexistent/report.json', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertIn('No files were read or exported', result.stdout)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
