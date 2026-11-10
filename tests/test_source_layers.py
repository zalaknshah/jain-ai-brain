"""Original synthetic examples; no real source corpus, filesystem or network."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from jace import source_layers as sl


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def span(raw, start, end):
    return {'start': start, 'end': end, 'span_sha256': digest(raw[start:end])}


def selection(raw, start=0, end=None):
    return {'source_sha256': digest(raw), **span(raw, start, len(raw) if end is None else end)}


def layer(raw, start, end, label='main_body'):
    return {**span(raw, start, end), 'layer': label}


class SourceLayerTests(unittest.TestCase):
    def test_complete_selection_is_not_review_approval(self):
        raw = b'Body text. Note text.'
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 11), layer(raw, 11, len(raw), 'editorial_note')])
        for key in ('selection_fully_partitioned', 'all_selection_non_whitespace_assigned',
                    'all_selection_non_whitespace_classified'):
            self.assertTrue(result[key])
        self.assertEqual(result['layer_counts']['main_body'], 1)
        self.assertEqual(result['layer_counts']['editorial_note'], 1)
        self.assertEqual(result['gaps'], [])
        for key in ('source_text_included', 'source_bytes_changed', 'scan_identity_verified',
                    'layer_labels_verified', 'scholarly_verified', 'runtime_admitted', 'training_admitted'):
            self.assertIs(result[key], False)
        self.assertNotIn('Body text', json.dumps(result))

    def test_whitespace_gaps_are_distinct_from_unassigned_text(self):
        raw = 'Body\r\n\t\u2003Note'.encode()
        note = raw.index(b'Note')
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 4), layer(raw, note, len(raw), 'editorial_note')])
        self.assertFalse(result['selection_fully_partitioned'])
        self.assertTrue(result['all_selection_non_whitespace_assigned'])
        self.assertTrue(result['all_selection_non_whitespace_classified'])
        self.assertEqual(result['gaps'], [{**span(raw, 4, note), 'byte_length': note - 4,
                                          'non_whitespace_characters': 0, 'whitespace_only': True}])

    def test_missing_text_is_never_absorbed_into_nearby_layers(self):
        raw = b'FIRST omitted LAST'
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 5), layer(raw, 14, len(raw))])
        self.assertEqual(result['unassigned_non_whitespace_characters'], 7)
        self.assertFalse(result['all_selection_non_whitespace_assigned'])
        self.assertFalse(result['all_selection_non_whitespace_classified'])
        self.assertEqual(result['gaps'][0]['span_sha256'], digest(b' omitted '))

    def test_unclassified_is_not_promoted_by_full_byte_coverage(self):
        raw = b'Unknown'
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 7, 'unclassified')])
        self.assertTrue(result['selection_fully_partitioned'])
        self.assertTrue(result['all_selection_non_whitespace_assigned'])
        self.assertFalse(result['all_selection_non_whitespace_classified'])
        self.assertEqual(result['unclassified_non_whitespace_characters'], 7)

    def test_unicode_byte_ranges_and_character_counts_are_distinct(self):
        raw = 'outside|śā字\r\n😀|outside'.encode()
        start, end = raw.index(b'|') + 1, raw.rindex(b'|')
        result = sl.audit_source_layers(raw, selection(raw, start, end), [layer(raw, start, end)])
        self.assertEqual(result['selection']['byte_length'], 13)
        self.assertEqual(result['selection']['non_whitespace_characters'], 4)
        self.assertEqual(result['selection']['span_sha256'], digest('śā字\r\n😀'.encode()))

    def test_no_layers_reports_the_whole_selection(self):
        raw = b'abc'
        result = sl.audit_source_layers(raw, selection(raw), [])
        self.assertEqual(result['gaps'], [result['selection']])
        self.assertFalse(result['all_selection_non_whitespace_classified'])

    def test_leading_and_trailing_gaps_are_not_lost(self):
        raw = b'left middle right'
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, 5, 11)])
        self.assertEqual([(r['start'], r['end']) for r in result['gaps']], [(0, 5), (11, 17)])
        self.assertEqual(result['unassigned_non_whitespace_characters'], 9)

    def test_all_fixed_labels_have_counts_and_no_correctness_claim(self):
        raw = b'abcdef'
        result = sl.audit_source_layers(raw, selection(raw), [layer(raw, i, i + 1, label) for i, label in enumerate(sl.LAYERS)])
        self.assertEqual(result['layer_counts'], dict.fromkeys(sl.LAYERS, 1))
        self.assertFalse(result['layer_labels_verified'])
        # Deliberately wrong caller labels are still just labels, not scan evidence.
        wrong = sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 6, 'running_header')])
        self.assertTrue(wrong['all_selection_non_whitespace_classified'])
        self.assertFalse(wrong['layer_labels_verified'])

    def test_source_and_span_hashes_fail_closed(self):
        raw = b'abc'
        for field in ('source_sha256', 'span_sha256'):
            selected = selection(raw); selected[field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selected, [])
        item = layer(raw, 0, 3); item['span_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, selection(raw), [item])
        for bad in ('A' * 64, '0' * 63, '0' * 64 + '\n', None, True, 1):
            selected = selection(raw); selected['source_sha256'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selected, [])

    def test_mid_character_endpoints_and_invalid_source_utf8_reject(self):
        raw = 'éX'.encode()
        for start, end in ((1, 3), (0, 1)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw, start, end), [])
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw), [layer(raw, start, end)])
        raw = b'good\xff'
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, selection(raw, 0, 4), [])

    def test_offsets_require_literal_integers_and_valid_intervals(self):
        raw = b'abc'
        for start, end in ((False, 3), (0, True), (0.0, 3), (0, 3.0), (-1, 3),
                           (0, 4), (1, 1), (2, 1), ('0', 3), (0, None)):
            selected = selection(raw); selected.update(start=start, end=end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selected, [])
            item = layer(raw, 0, 3); item.update(start=start, end=end)
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw), [item])

    def test_overlap_duplicates_reversal_and_outside_selection_reject(self):
        raw = b'abcdefgh'
        cases = [[layer(raw, 2, 5), layer(raw, 4, 6)], [layer(raw, 2, 5)] * 2,
                 [layer(raw, 4, 6), layer(raw, 2, 4)], [layer(raw, 1, 4)], [layer(raw, 4, 7)]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw, 2, 6), rows)

    def test_unknown_or_missing_fields_and_labels_reject(self):
        raw = b'abc'
        for field in ('source_sha256', 'start', 'end', 'span_sha256'):
            selected = selection(raw); selected.pop(field)
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selected, [])
        for extra in ('verified', 'runtime_admitted', 'text', 'path'):
            selected = selection(raw); selected[extra] = True
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selected, [])
            row = layer(raw, 0, 3); row[extra] = True
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw), [row])
        for label in ('approved', '', 'MAIN_BODY', None, [], 1):
            with self.subTest(label=label), self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw), [layer(raw, 0, 3, label)])

    def test_exact_collection_types_and_source_bounds(self):
        raw = b'x'
        for bad in ('x', bytearray(raw), memoryview(raw), None, b'', b'x' * (sl.MAX_SOURCE_BYTES + 1)):
            with self.assertRaises(ValueError):
                sl.audit_source_layers(bad, selection(raw), [])
        for bad in ((), iter([]), None, {}, 'layers'):
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, selection(raw), bad)
        for bad in ([], None, 'selection'):
            with self.assertRaises(ValueError):
                sl.audit_source_layers(raw, bad, [])
        class DictSubclass(dict):
            pass
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, DictSubclass(selection(raw)), [])
        raw = b'x' * sl.MAX_SOURCE_BYTES
        self.assertEqual(sl.audit_source_layers(raw, selection(raw, 0, 1), [])['source_byte_length'], sl.MAX_SOURCE_BYTES)

    def test_selection_and_layer_count_boundaries(self):
        raw = b'x' * (sl.MAX_SELECTION_BYTES + 1)
        sl.audit_source_layers(raw, selection(raw, 0, sl.MAX_SELECTION_BYTES), [])
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, selection(raw), [])
        raw = b'x' * 257
        sl.audit_source_layers(raw, selection(raw), [layer(raw, i, i + 1) for i in range(256)])
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, selection(raw), [layer(raw, i, i + 1) for i in range(257)])
        raw = '\r\n\u2003'.encode()
        with self.assertRaises(ValueError):
            sl.audit_source_layers(raw, selection(raw), [])

    def test_field_names_reject_subclasses_and_custom_equality(self):
        class StringKey(str):
            pass
        class ForeignKey:
            def __hash__(self):
                return hash('start')
            def __eq__(self, other):
                raise AssertionError('caller key equality must not run')
        raw = b'x'
        for base in (selection(raw), layer(raw, 0, 1)):
            for key in (StringKey('start'), ForeignKey()):
                changed = {name: value for name, value in base.items() if name != 'start'}
                changed[key] = 0
                with self.subTest(key=type(key).__name__), self.assertRaises(ValueError):
                    if 'source_sha256' in base:
                        sl.audit_source_layers(raw, changed, [])
                    else:
                        sl.audit_source_layers(raw, selection(raw), [changed])

    def test_no_io_or_input_mutation_or_retained_mutable_references(self):
        raw = b'original synthetic text'
        selected = selection(raw); rows = [layer(raw, 0, len(raw))]
        original = copy.deepcopy((selected, rows))
        with patch('builtins.open', side_effect=AssertionError('IO forbidden')):
            result = sl.audit_source_layers(raw, selected, rows)
        self.assertEqual((selected, rows), original)
        result['layers'][0]['start'] = 99
        result['selection']['end'] = 99
        result['limits'].clear()
        self.assertEqual((selected, rows), original)
        self.assertTrue(sl.LIMITATIONS)


if __name__ == '__main__':
    unittest.main()
