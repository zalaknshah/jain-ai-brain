"""Original synthetic fixtures only; no scan, source collection or network."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from jace import source_anchors as anchors


def passage(prefix, count=24):
    return ' '.join(f'{prefix}{number}' for number in range(count))


class SourceAnchorTests(unittest.TestCase):
    def test_exact_ordered_pages_bind_source_bytes_without_returning_content(self):
        pages = [passage('alpha'), passage('beta')]
        raw = ('\n\t'.join(pages)).encode()
        result = anchors.find_source_anchors(raw, pages)
        self.assertEqual(result['counts']['interior_span_candidate'], 2)
        for item, expected in zip(result['pages'], pages):
            span = raw[item['source_byte_start']:item['source_byte_end']]
            self.assertEqual(span.decode(), expected)
            self.assertEqual(item['source_span_sha256'], hashlib.sha256(span).hexdigest())
            self.assertEqual(item['exact_matched_page_ocr_words'], 24)
            for anchor in item['anchors']:
                fragment = raw[anchor['source_byte_start']:anchor['source_byte_end']]
                start = anchor['page_word_start']
                self.assertEqual(fragment.decode().split(), expected.split()[start:start + 8])
                self.assertEqual(anchor['source_span_sha256'], hashlib.sha256(fragment).hexdigest())
        self.assertNotIn('alpha0', json.dumps(result))
        self.assertFalse(result['source_text_included'])
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())

    def test_multibyte_offsets_preserve_original_spacing_and_line_endings(self):
        words = [f'śabda{n}字' for n in range(20)]
        source = 'PREFIX\r\n' + '\t  \r\n'.join(words) + '\nSUFFIX'
        result = anchors.find_source_anchors(source.encode(), [' '.join(words)])
        row = result['pages'][0]
        self.assertEqual(row['status'], 'interior_span_candidate')
        self.assertEqual(row['source_byte_start'], len('PREFIX\r\n'.encode()))
        self.assertEqual(source.encode()[row['source_byte_start']:row['source_byte_end']].decode(), '\t  \r\n'.join(words))

    def test_repeated_source_anchors_never_infer_a_unique_location(self):
        text = passage('duplicate')
        result = anchors.find_source_anchors((text + '\n' + text).encode(), [text])
        self.assertEqual(result['pages'][0]['status'], 'unresolved')
        self.assertEqual(result['pages'][0]['unique_exact_anchor_matches'], 0)
        self.assertNotIn('source_byte_start', result['pages'][0])

    def test_short_and_empty_pages_are_not_fabricated(self):
        result = anchors.find_source_anchors(passage('word').encode(), ['', ' \n\t ', passage('word', 8), 'unknown text'])
        self.assertEqual([p['status'] for p in result['pages']], ['empty_page_text', 'empty_page_text', 'unresolved', 'unresolved'])
        self.assertEqual(sum(result['counts'].values()), 4)

    def test_duplicate_or_reordered_pages_are_all_marked_conflicting(self):
        a, b = passage('a'), passage('b')
        for pages in ([a, a], [b, a], [a, b, a]):
            with self.subTest(pages=pages):
                result = anchors.find_source_anchors((a + ' ' + b).encode(), pages)
                self.assertTrue(all(p['status'] == 'conflicting_page_candidate' for p in result['pages']))

    def test_earlier_overlap_is_not_hidden_by_intervening_conflicts(self):
        words = passage('word', 160).split()
        pages = [' '.join(words[10:80]), ' '.join(words[100:130]),
                 ' '.join(words[20:40]), ' '.join(words[50:70])]
        result = anchors.find_source_anchors(' '.join(words).encode(), pages)
        self.assertTrue(all(p['status'] == 'conflicting_page_candidate' for p in result['pages']))

    def test_reordered_anchors_within_page_remain_unresolved(self):
        a, b = passage('a'), passage('b')
        result = anchors.find_source_anchors((a + ' ' + b).encode(), [b + ' ' + a])
        self.assertEqual(result['pages'][0]['status'], 'unresolved')

    def test_ocr_difference_can_make_a_repeated_phrase_spuriously_unique_elsewhere(self):
        repeated = 'review this synthetic placeholder phrase before moving forward'
        noisy = repeated.replace('review', 'rev1ew')
        left, right = passage('targetleft'), passage('targetright')
        earlier = passage('earlier') + ' ' + repeated + ' ' + passage('earlierend')
        source = (earlier + ' ' + left + ' ' + noisy + ' ' + right).encode()
        page = left + ' ' + repeated + ' ' + right
        result = anchors.find_source_anchors(source, [page])
        self.assertGreater(result['pages'][0]['unique_exact_anchor_matches'], 20)
        self.assertEqual(result['pages'][0]['status'], 'unresolved')
        self.assertNotIn('source_byte_start', result['pages'][0])
        # Retaining the original OCR version restores ordered literal agreement.
        literal = anchors.find_source_anchors(source, [left + ' ' + noisy + ' ' + right])
        self.assertEqual(literal['pages'][0]['status'], 'interior_span_candidate')

    def test_unique_matches_do_not_certify_intended_scan_page_identity(self):
        intended_print = passage('repeat')
        intended_ocr = intended_print.replace('repeat', 'repea7')
        prefix = intended_ocr + ' separator '
        source = (prefix + intended_print).encode()
        result = anchors.find_source_anchors(source, [intended_print])
        row = result['pages'][0]
        # Without the scan, the helper cannot know whether the page actually
        # belongs to the noisy first copy. It must not certify this coincidence.
        self.assertEqual(row['status'], 'interior_span_candidate')
        self.assertEqual(row['source_byte_start'], len(prefix.encode()))
        self.assertFalse(row['scan_accuracy_reviewed'])
        self.assertFalse(row['source_layers_separated'])
        self.assertFalse(row['runtime_admitted'])
        self.assertFalse(row['training_admitted'])

    def test_wide_source_gap_does_not_join_distant_passages(self):
        a, b = passage('a', 8), passage('b', 8)
        raw = (a + ' ' + passage('gap', 100) + ' ' + b).encode()
        result = anchors.find_source_anchors(raw, [a + ' ' + b])
        self.assertEqual(result['pages'][0]['status'], 'unresolved')

    def test_unknown_margins_are_not_inferred_as_page_boundaries(self):
        page = 'unmatched opening ' + passage('known') + ' unmatched ending'
        result = anchors.find_source_anchors(('source prefix ' + passage('known') + ' source suffix').encode(), [page])
        row = result['pages'][0]
        self.assertEqual(row['status'], 'interior_span_candidate')
        self.assertEqual(row['anchors'][0]['page_word_start'], 2)
        self.assertEqual(row['exact_matched_page_ocr_words'], 24)
        self.assertIn('not a complete page', result['limits'][0])

    def test_no_case_spelling_or_unicode_composition_normalization(self):
        original = ' '.join(f'café{n}' for n in range(24))
        for changed in (original.upper(), original.replace('é', 'e\u0301'), original.replace('café', 'cafe')):
            with self.subTest(changed=changed):
                result = anchors.find_source_anchors(original.encode(), [changed])
                self.assertEqual(result['pages'][0]['status'], 'unresolved')

    def test_input_types_unicode_and_parameter_bounds_fail_closed(self):
        valid = passage('word').encode()
        for raw in (b'', bytearray(valid), 'text', None, b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                anchors.find_source_anchors(raw, ['text'])
        for pages in ([], (), 'text', None, [None], [b'text'], ['\ud800']):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                anchors.find_source_anchors(valid, pages)
        for size in (True, 0, 3, 17, 8.0, '8', None):
            with self.subTest(size=size), self.assertRaises(ValueError):
                anchors.find_source_anchors(valid, ['text'], anchor_words=size)

    def test_input_work_budgets_are_enforced(self):
        raw = passage('word').encode()
        cases = [('MAX_SOURCE_BYTES', len(raw)-1, raw, ['text']),
                 ('MAX_SOURCE_WORDS', 23, raw, ['text']),
                 ('MAX_PAGES', 1, raw, ['', '']),
                 ('MAX_PAGE_CHARACTERS', 3, raw, ['word']),
                 ('MAX_PAGE_TEXT_BYTES', 3, raw, ['é', 'é'])]
        for name, limit, source, pages in cases:
            with self.subTest(name=name), patch.object(anchors, name, limit), self.assertRaises(ValueError):
                anchors.find_source_anchors(source, pages)

    def test_no_input_mutation_or_admission_and_results_are_independent(self):
        raw = passage('word').encode(); pages = [raw.decode()]; before = copy.deepcopy(pages)
        first = anchors.find_source_anchors(raw, pages)
        second = anchors.find_source_anchors(raw, pages)
        first['pages'][0]['runtime_admitted'] = True
        first['limits'].clear()
        self.assertEqual(pages, before)
        for flag in ('runtime_admitted', 'training_admitted', 'scan_accuracy_reviewed', 'source_layers_separated'):
            self.assertIs(second['pages'][0][flag], False)
        self.assertFalse(second['source_bytes_changed'])
        self.assertEqual(anchors.find_source_anchors(raw, pages), second)

    def test_anchor_word_boundaries_are_supported(self):
        text = passage('word', 40)
        for size in (4, 8, 16):
            with self.subTest(size=size):
                result = anchors.find_source_anchors(text.encode(), [text], anchor_words=size)
                self.assertEqual(result['pages'][0]['status'], 'interior_span_candidate')
                self.assertEqual(result['anchor_words'], size)


if __name__ == '__main__':
    unittest.main()
