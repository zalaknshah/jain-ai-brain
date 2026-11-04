"""Original synthetic bytes only: no religious source material is included."""
import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jace import source_bundle as sb


TEXT = '  Original synthetic fixture.\r\nCarefully preserve café, 雪, and spaces.\t\n'
DATA = TEXT.encode('utf-8')
DIGEST = hashlib.sha256(DATA).hexdigest()


def record(digest=DIGEST, end=len(DATA), **changes):
    result = {'entry_id': 'synthetic:one', 'title': 'Synthetic fixture',
              'guidance': 'Original example only.', 'source': 'Original synthetic text',
              'work': 'Synthetic source work', 'language': 'en', 'location': 'Fixture paragraph 1',
              'license': 'Operator-declared synthetic fixture rights', 'verified': True,
              'source_ref': {'sha256': digest, 'start': 0, 'end': end}}
    result.update(changes)
    return result


def manifest(records=None):
    return {'format': sb.FORMAT, 'sources': [{'path': f'sources/{DIGEST}.txt', 'sha256': DIGEST}],
            'records': [record()] if records is None else records}


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        (self.bundle / 'sources').mkdir()
        self.source = self.bundle / 'sources' / (DIGEST + '.txt')
        self.source.write_bytes(DATA)
        self.path = self.bundle / 'bundle.json'
        self.save(manifest())

    def save(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def assert_bad(self):
        with self.assertRaises(ValueError):
            sb.load_source_bundle(self.path)

    def test_exact_original_bytes_crlf_whitespace_and_defaults(self):
        loaded, trusted = sb.load_corpus_snapshot(self.path)
        self.assertTrue(trusted)
        value = loaded[0]
        self.assertEqual(value['principle'], TEXT)
        self.assertEqual(value['principle'].encode('utf-8'), DATA)
        self.assertEqual((value['source_sha256'], value['source_byte_start'], value['source_byte_end']),
                         (DIGEST, 0, len(DATA)))
        self.assertEqual(value['tags'], [])
        self.assertIsNone(value['edition'])
        self.assertNotIn('source_ref', value)
        self.assertNotIn(str(self.root), json.dumps(value))
        self.assertEqual(sb.load_corpus_records(self.path), loaded)

    def test_valid_subspan_derives_passage_not_guidance(self):
        value = manifest()
        start = DATA.index('café'.encode())
        value['records'][0]['source_ref'].update(start=start, end=start + len('café'.encode()))
        self.save(value)
        self.assertEqual(sb.load_source_bundle(self.path)[0]['principle'], 'café')

    def test_metadata_normalizes_but_passage_does_not(self):
        value = manifest([record(title='  Synthetic\n  fixture  ', tags=['  one\t tag  '], edition=' test  edition ')])
        self.save(value)
        loaded = sb.load_source_bundle(self.path)[0]
        self.assertEqual(loaded['title'], 'Synthetic fixture')
        self.assertEqual(loaded['tags'], ['one tag'])
        self.assertEqual(loaded['edition'], 'test edition')
        self.assertEqual(loaded['principle'], TEXT)

    def test_legacy_snapshot_has_no_trusted_flag(self):
        legacy = [{'entry_id': 'untrusted', 'source_sha256': DIGEST}]
        self.save(legacy)
        self.assertEqual(sb.load_corpus_snapshot(self.path), (legacy, False))
        self.assert_bad()

    def test_digest_tampering_and_invalid_utf8(self):
        for data in [DATA.replace(b'Original', b'Changed!'), b'\xff']:
            with self.subTest(data=data):
                self.source.write_bytes(data)
                self.assert_bad()
        invalid = b'\xffsynthetic'
        digest = hashlib.sha256(invalid).hexdigest()
        self.source.unlink()
        (self.source.parent / (digest + '.txt')).write_bytes(invalid)
        value = manifest([record(digest=digest, end=len(invalid))])
        value['sources'] = [{'path': f'sources/{digest}.txt', 'sha256': digest}]
        self.save(value)
        self.assert_bad()

    def test_utf8_spans_are_byte_offsets_and_cannot_cut_characters(self):
        at = DATA.index('é'.encode())
        for start, end in [(at + 1, at + 2), (at, at + 1), (-1, 1), (1, 1), (2, 1),
                           (0, len(DATA) + 1), (False, 5), (0, True), (0.0, 4), (0, 4.0)]:
            with self.subTest(start=start, end=end):
                value = manifest()
                value['records'][0]['source_ref'].update(start=start, end=end)
                self.save(value)
                self.assert_bad()

    def test_spans_reject_empty_whitespace_controls_and_lone_cr(self):
        for text in ['  \t\n', 'synthetic\rline', 'synthetic\x1bline', 'synthetic\u202eline']:
            data = text.encode(); digest = hashlib.sha256(data).hexdigest()
            with self.subTest(text=text), self.assertRaises(ValueError):
                sb.write_source_bundle(self.root / 'out', {digest: data}, [record(digest, len(data))])
        self.assertFalse((self.root / 'out').exists())

    def test_required_fields_unknown_fields_false_review_and_rights(self):
        for field in record():
            value = manifest(); del value['records'][0][field]
            with self.subTest(missing=field):
                self.save(value); self.assert_bad()
        for field, value in [('verified', False), ('verified', 1), ('verified', 'true'), ('license', ''),
                             ('work', None), ('source', ' '), ('language', ''), ('location', ''),
                             ('principle', 'Invented replacement'), ('source_sha256', DIGEST),
                             ('source_path', '/private/path'), ('entry_id', 'bad[id]'),
                             ('entry_id', 'two words'), ('tags', ['one', ' one ']), ('edition', ''),
                             ('title', 'unsafe\rmetadata'), ('title', '\ud800')]:
            with self.subTest(field=field, value=value):
                item = manifest(); item['records'][0][field] = value
                # ensure_ascii allows us to test lone surrogate JSON safely.
                self.path.write_text(json.dumps(item), encoding='utf-8')
                self.assert_bad()
        for where in ['top', 'source', 'ref']:
            value = manifest()
            target = value if where == 'top' else value['sources'][0] if where == 'source' else value['records'][0]['source_ref']
            target['unknown'] = 'field'
            self.save(value); self.assert_bad()

    def test_duplicate_ids_declarations_json_keys_and_nonfinite(self):
        value = manifest([record(), record()]); self.save(value); self.assert_bad()
        value = manifest(); value['sources'].append(copy.deepcopy(value['sources'][0]))
        self.save(value); self.assert_bad()
        for raw in ['{"format":"x","format":"y"}', '{"x":NaN}', '{"x":Infinity}',
                    '{"x":-Infinity}', '[{"x":1e999}]', '\ufeff{}', '{broken', '[' * 2000 + ']' * 2000]:
            with self.subTest(raw=raw[:40]):
                self.path.write_text(raw, encoding='utf-8')
                with self.assertRaises(ValueError):
                    sb.load_corpus_snapshot(self.path)

    def test_declared_paths_cannot_escape_or_alias(self):
        (self.root / 'outside.txt').write_bytes(DATA)
        for path in ['../outside.txt', '/etc/passwd', f'sources/../sources/{DIGEST}.txt',
                     f'sources//{DIGEST}.txt', f'sources/./{DIGEST}.txt', f'sources\\{DIGEST}.txt',
                     f'sources/{DIGEST.upper()}.txt', f'sources/{DIGEST}.txt/extra']:
            with self.subTest(path=path):
                value = manifest(); value['sources'][0]['path'] = path
                self.save(value); self.assert_bad()
        value = manifest(); value['sources'][0]['sha256'] = DIGEST.upper()
        self.save(value); self.assert_bad()
        with self.assertRaises(ValueError):
            sb.load_source_bundle(self.bundle / '..' / 'bundle' / 'bundle.json')

    def test_undeclared_and_unreferenced_sources_rejected(self):
        extra = b'Another original fixture.'; digest = hashlib.sha256(extra).hexdigest()
        (self.source.parent / (digest + '.txt')).write_bytes(extra)
        self.assert_bad()
        value = manifest(); value['sources'].append({'path': f'sources/{digest}.txt', 'sha256': digest})
        self.save(value); self.assert_bad()
        value['records'].append(record(digest, len(extra), entry_id='synthetic:two'))
        self.save(value)
        self.assertEqual(len(sb.load_source_bundle(self.path)), 2)

    def test_symlinks_at_root_intermediate_and_final_components(self):
        alias = self.root / 'alias'; alias.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaises(ValueError):
            sb.load_source_bundle(alias / 'bundle.json')
        linked_parent = self.root / 'parent-alias'; linked_parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            sb.load_source_bundle(linked_parent / 'bundle' / 'bundle.json')
        manifest_backup = self.bundle / 'original.json'; self.path.rename(manifest_backup)
        self.path.symlink_to(manifest_backup)
        self.assert_bad(); self.path.unlink(); manifest_backup.rename(self.path)
        source_backup = self.root / 'original.txt'; self.source.rename(source_backup)
        self.source.symlink_to(source_backup)
        self.assert_bad(); self.source.unlink(); source_backup.rename(self.source)
        directory_backup = self.root / 'original-sources'; self.source.parent.rename(directory_backup)
        (self.bundle / 'sources').symlink_to(directory_backup, target_is_directory=True)
        self.assert_bad()

    def test_hardlinks_manifest_and_source_are_rejected(self):
        extra = self.root / 'hardlink'
        os.link(self.path, extra); self.assert_bad(); extra.unlink()
        os.link(self.source, extra); self.assert_bad()

    def test_special_files_rejected_without_blocking(self):
        self.source.unlink(); os.mkfifo(self.source)
        self.assert_bad()

    def test_manifest_mutation_during_read_is_detected(self):
        original = os.read; modified = False
        def change(fd, size):
            nonlocal modified
            data = original(fd, size)
            if not modified and data.startswith(b'{'):
                modified = True
                with self.path.open('ab') as stream:
                    stream.write(b' ')
            return data
        with patch.object(sb.os, 'read', side_effect=change):
            self.assert_bad()
        self.assertTrue(modified)

    def test_source_mutation_or_replacement_during_read_is_detected(self):
        for replacement in [False, True]:
            self.source.write_bytes(DATA)
            original = os.read; modified = False
            def change(fd, size):
                nonlocal modified
                data = original(fd, size)
                if not modified and data.startswith(b'  Original'):
                    modified = True
                    if replacement:
                        self.source.unlink()
                        self.source.write_bytes(DATA)
                    else:
                        with self.source.open('r+b') as stream:
                            stream.write(b'!!')
                return data
            with self.subTest(replacement=replacement), patch.object(sb.os, 'read', side_effect=change):
                self.assert_bad()
            self.assertTrue(modified)

    def test_source_directory_replacement_after_open_does_not_redirect_reads(self):
        original = sb._read_regular; changed = False
        def replace(parent, name, limit, chain):
            nonlocal changed
            if name.endswith('.txt') and not changed:
                changed = True
                self.source.parent.rename(self.root / 'pinned-sources')
                self.source.parent.mkdir()
                self.source.write_bytes(DATA)
            return original(parent, name, limit, chain)
        with patch.object(sb, '_read_regular', side_effect=replace):
            self.assert_bad()
        self.assertTrue(changed)

    def test_manifest_mutation_after_read_is_detected_by_final_guard(self):
        original = sb._validated_records
        def change(records, sources):
            result = original(records, sources)
            self.path.write_bytes(self.path.read_bytes() + b' ')
            return result
        with patch.object(sb, '_validated_records', side_effect=change):
            self.assert_bad()

    def test_reads_still_bound_when_stat_size_is_stale(self):
        self.source.write_bytes(b'x' * 129)
        original_stat = os.fstat; original_read = os.read; sizes = []
        def stale(fd):
            info = original_stat(fd)
            if stat.S_ISREG(info.st_mode) and info.st_size == 129:
                return SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino, st_mode=info.st_mode,
                                       st_nlink=info.st_nlink, st_size=1, st_mtime_ns=info.st_mtime_ns,
                                       st_ctime_ns=info.st_ctime_ns)
            return info
        def bounded(fd, size):
            sizes.append(size)
            return original_read(fd, size)
        with patch.object(sb, 'MAX_SOURCE_BYTES', 128), patch.object(sb.os, 'fstat', side_effect=stale), \
                patch.object(sb.os, 'read', side_effect=bounded):
            self.assert_bad()
        self.assertTrue(all(0 < size <= sb._READ_CHUNK for size in sizes))

    def test_resource_limits_are_checked_at_boundary(self):
        cases = [('MAX_MANIFEST_BYTES', self.path.stat().st_size - 1), ('MAX_SOURCE_BYTES', len(DATA) - 1),
                 ('MAX_TOTAL_SOURCE_BYTES', len(DATA) - 1), ('MAX_PASSAGE_BYTES', len(DATA) - 1),
                 ('MAX_PASSAGE_CHARS', len(TEXT) - 1), ('MAX_SOURCES', 0), ('MAX_RECORDS', 0)]
        for name, maximum in cases:
            with self.subTest(name=name), patch.object(sb, name, maximum):
                self.assert_bad()
        for name, maximum in [('MAX_MANIFEST_BYTES', self.path.stat().st_size),
                              ('MAX_SOURCE_BYTES', len(DATA)), ('MAX_TOTAL_SOURCE_BYTES', len(DATA)),
                              ('MAX_PASSAGE_BYTES', len(DATA)), ('MAX_PASSAGE_CHARS', len(TEXT))]:
            with self.subTest(name=name), patch.object(sb, name, maximum):
                self.assertEqual(sb.load_source_bundle(self.path)[0]['principle'], TEXT)
        for field in ['sources', 'records']:
            value = manifest(); value[field] = []
            self.save(value); self.assert_bad()

    def test_source_reader_uses_exact_utf8_bytes_and_rejects_unsafe_files(self):
        self.assertEqual(sb.read_source_file(self.source), DATA)
        alias = self.root / 'source-alias'; alias.symlink_to(self.source)
        with self.assertRaises(ValueError): sb.read_source_file(alias)
        for data in [b'', b'\xff', b'x' * (sb.MAX_SOURCE_BYTES + 1)]:
            self.source.write_bytes(data)
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                sb.read_source_file(self.source)

    def test_actual_count_size_and_passage_limits(self):
        value = manifest([record(entry_id=f'synthetic:{index}') for index in range(sb.MAX_RECORDS + 1)])
        self.save(value); self.assert_bad()
        value = manifest(); value['sources'] *= sb.MAX_SOURCES + 1
        self.save(value); self.assert_bad()
        self.save(manifest())
        with self.source.open('wb') as stream: stream.truncate(sb.MAX_SOURCE_BYTES + 1)
        self.assert_bad()
        self.source.write_bytes(DATA)
        with self.path.open('wb') as stream: stream.truncate(sb.MAX_MANIFEST_BYTES + 1)
        self.assert_bad()
        for text in ['x' * (sb.MAX_PASSAGE_CHARS + 1), '😀' * 17000]:
            data = text.encode(); digest = hashlib.sha256(data).hexdigest()
            with self.subTest(bytes=len(data)), self.assertRaises(ValueError):
                sb.write_source_bundle(self.root / 'too-large', {digest: data}, [record(digest, len(data))])

    def test_total_limit_counts_all_sources(self):
        extra = b'Another original fixture.'; digest = hashlib.sha256(extra).hexdigest()
        (self.source.parent / (digest + '.txt')).write_bytes(extra)
        value = manifest([record(), record(digest, len(extra), entry_id='synthetic:two')])
        value['sources'].append({'path': f'sources/{digest}.txt', 'sha256': digest})
        self.save(value)
        with patch.object(sb, 'MAX_TOTAL_SOURCE_BYTES', len(DATA) + len(extra) - 1): self.assert_bad()
        with patch.object(sb, 'MAX_TOTAL_SOURCE_BYTES', len(DATA) + len(extra)):
            self.assertEqual(len(sb.load_source_bundle(self.path)), 2)

    def test_nested_json_keys_and_escaped_structure(self):
        raw = json.dumps(manifest()).replace('"verified": true', '"verified": true, "verified": true')
        self.path.write_text(raw, encoding='utf-8'); self.assert_bad()
        value = manifest([record(guidance='Escaped "[{}]" original example.')])
        self.save(value)
        self.assertEqual(sb.load_source_bundle(self.path)[0]['guidance'], value['records'][0]['guidance'])

    def test_source_removed_after_read_is_rejected(self):
        original = sb._validated_records
        def remove(records, sources):
            result = original(records, sources)
            self.source.unlink()
            return result
        with patch.object(sb, '_validated_records', side_effect=remove): self.assert_bad()

    def test_unsupported_io_fails_closed(self):
        with patch.object(sb.os, 'supports_dir_fd', set()), self.assertRaises(ValueError):
            sb.load_source_bundle(self.path)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.target = self.root / 'published'

    def write(self):
        return sb.write_source_bundle(self.target, {DIGEST: DATA}, [record()])

    def assert_rolled_back(self):
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.root.glob('.jace-source-*')), [])

    def test_export_is_private_deterministic_and_loadable(self):
        path = self.write()
        self.assertEqual(path, self.target / 'bundle.json')
        self.assertEqual(sb.load_source_bundle(path)[0]['principle'], TEXT)
        second = sb.write_source_bundle(self.root / 'second', {DIGEST: DATA}, [record()])
        self.assertEqual(path.read_bytes(), second.read_bytes())
        for child in [self.target, self.target / 'sources']:
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o700)
        for child in [path, self.target / 'sources' / (DIGEST + '.txt')]:
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600)
        self.assertEqual(list(self.root.glob('.jace-source-*')), [])

    def test_existing_file_directory_and_dangling_symlink_never_overwritten(self):
        for kind in ['directory', 'file', 'symlink']:
            if kind == 'directory': self.target.mkdir()
            elif kind == 'file': self.target.write_bytes(b'keep existing data')
            else: self.target.symlink_to(self.root / 'does-not-exist')
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.write()
            if kind == 'directory': self.target.rmdir()
            elif kind == 'file':
                self.assertEqual(self.target.read_bytes(), b'keep existing data'); self.target.unlink()
            else:
                self.assertTrue(self.target.is_symlink()); self.target.unlink()
            self.assertEqual(list(self.root.glob('.jace-source-*')), [])

    def test_existing_destination_race_is_atomic_no_overwrite(self):
        original = sb._rename_noreplace
        def race(parent, stage, target):
            self.target.mkdir()
            (self.target / 'keep.txt').write_text('Keep concurrent data.')
            return original(parent, stage, target)
        with patch.object(sb, '_rename_noreplace', side_effect=race), self.assertRaises(ValueError):
            self.write()
        self.assertEqual((self.target / 'keep.txt').read_text(), 'Keep concurrent data.')
        self.assertEqual(list(self.root.glob('.jace-source-*')), [])

    def test_output_parent_symlink_and_traversal_rejected(self):
        alias = self.root / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        for target in [alias / 'new', self.root / '..' / self.root.name / 'new']:
            with self.subTest(target=target), self.assertRaises(ValueError):
                sb.write_source_bundle(target, {DIGEST: DATA}, [record()])
        self.assertFalse((self.root / 'new').exists())

    def test_invalid_input_never_creates_target_or_stage(self):
        cases = [({}, [record()]), ({DIGEST: b'changed'}, [record()]), ({DIGEST: DATA}, []),
                 ({DIGEST: DATA}, [record(verified=False)]), ({DIGEST: bytearray(DATA)}, [record()]),
                 ({DIGEST: DATA}, [record(principle='Invented quote')])]
        for sources, records in cases:
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                sb.write_source_bundle(self.target, sources, records)
            self.assert_rolled_back()

    def test_write_and_fsync_failures_roll_back_private_stage(self):
        for operation in ['_write_private', '_rename_noreplace']:
            with self.subTest(operation=operation), patch.object(sb, operation, side_effect=OSError('injected failure')), \
                    self.assertRaises(ValueError):
                self.write()
            self.assert_rolled_back()
        with patch.object(sb.os, 'fsync', side_effect=OSError('injected fsync failure')), self.assertRaises(ValueError):
            self.write()
        self.assert_rolled_back()

    def test_partial_write_failure_rolls_back(self):
        original = os.write; calls = 0
        def fail(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1: return original(fd, data[:3])
            raise OSError('injected write failure')
        with patch.object(sb.os, 'write', side_effect=fail), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()

    def test_written_manifest_tampering_rolls_back(self):
        original = sb._write_private
        def tamper(parent, name, data):
            if name == 'bundle.json': data += b' '
            return original(parent, name, data)
        with patch.object(sb, '_write_private', side_effect=tamper), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()

    def test_unsupported_atomic_publish_rolls_back_without_fallback(self):
        with patch.object(sb.sys, 'platform', 'unsupported'), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()
        with patch.object(sb.ctypes, 'CDLL', return_value=SimpleNamespace()), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()

    def test_written_source_tampering_rolls_back(self):
        original = sb._write_private
        def tamper(parent, name, data):
            if name.endswith('.txt'): data = b'Changed synthetic source.'
            return original(parent, name, data)
        with patch.object(sb, '_write_private', side_effect=tamper), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()

    def test_zero_progress_write_rolls_back(self):
        with patch.object(sb.os, 'write', return_value=0), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()

    def test_missing_parent_fails_without_creating_directories(self):
        with self.assertRaises(ValueError):
            sb.write_source_bundle(self.root / 'missing' / 'new', {DIGEST: DATA}, [record()])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_manifest_output_limit_is_applied_before_staging(self):
        with patch.object(sb, 'MAX_MANIFEST_BYTES', 1), self.assertRaises(ValueError): self.write()
        self.assert_rolled_back()


if __name__ == '__main__':
    unittest.main()
