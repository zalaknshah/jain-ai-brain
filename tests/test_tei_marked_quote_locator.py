import hashlib
import unittest
from scripts.locate_tei_terms import locate


def source(body):
    return ('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><quote type="base-text">target</quote></teiHeader><text><body>' + body + '</body></text></TEI>').encode()


def lookup(data, query='target', **kwargs):
    return locate(data, hashlib.sha256(data).hexdigest(), query,
                  scope='marked-base-text-quotes', **kwargs)


class MarkedQuoteLocatorTests(unittest.TestCase):
    def test_commentary_and_unmarked_quotes_excluded(self):
        data = source('<lg>target</lg><quote>target</quote><quote type="Base-Text">target</quote><quote type="base-text"><lg>target</lg></quote>')
        result = lookup(data)
        self.assertEqual(result['units_examined'], 1)
        self.assertEqual(result['matching_units'], 1)
        self.assertEqual(result['matches'][0]['unit_index'], 1)
        self.assertEqual(result['matches'][0]['character_offsets'], [0])
        self.assertNotIn('groups_examined', result)
        for key in ('source_markup_verified', 'training_admitted', 'runtime_admitted', 'translation_verified'):
            self.assertIs(result[key], False)

    def test_default_unchanged(self):
        data = source('<quote type="base-text">target</quote><lg>target</lg>')
        result = locate(data, hashlib.sha256(data).hexdigest(), 'target')
        self.assertEqual(result['format'], 'jace-literal-tei-locator-v1')
        self.assertEqual(result['groups_examined'], 1)
        self.assertNotIn('scope', result)

    def test_nested_units_are_distinct_not_unique_lexical_entries(self):
        result = lookup(source('<quote type="base-text">x<quote type="base-text">target</quote></quote>'))
        self.assertEqual(result['matching_units'], 2)
        self.assertEqual([m['unit_index'] for m in result['matches']], [1, 2])
        self.assertEqual([m['character_offsets'] for m in result['matches']], [[1], [0]])

    def test_scope_and_digest_fail_closed(self):
        data = source('<quote type="base-text">target</quote>')
        with self.assertRaises(ValueError):
            locate(data, hashlib.sha256(data).hexdigest(), 'target', scope='all')
        with self.assertRaises(ValueError):
            locate(data, '0'*64, 'target', scope='marked-base-text-quotes')

    def test_bounds_and_no_source_echo(self):
        data = source(''.join('<quote type="base-text" n="secret">' + 'x'*100 + '</quote>' for _ in range(20)))
        result = lookup(data, 'x', limit=10)
        self.assertTrue(result['truncated'])
        self.assertEqual(sum(len(m['character_offsets']) for m in result['matches']), 512)
        self.assertTrue(all(m['offsets_truncated'] for m in result['matches']))
        self.assertNotIn('secret', str(result))
        self.assertNotIn('x'*100, str(result))

    def test_no_marked_units_is_not_missing_word_claim(self):
        result = lookup(source('<lg>target</lg>'))
        self.assertEqual(result['units_examined'], 0)
        self.assertEqual(result['matches'], [])
