import unittest
from unittest.mock import patch
from jace.canonical import CanonicalStore
from jace.models import CanonicalEntry


def entry(identifier, **fields):
    values = dict(entry_id=identifier, title='Neutral', principle='Unrelated passage',
                  guidance='Ordinary guidance', source='Synthetic source', tags=[])
    values.update(fields)
    return CanonicalEntry(**values)


def store(*entries):
    result = CanonicalStore.__new__(CanonicalStore)
    result._entries = tuple(entries)
    result.source_bound = False
    return result


class LexicalExplanationsTests(unittest.TestCase):
    def test_metadata_does_not_become_passage_match(self):
        original = entry('a', title='Compassion', tags=['compassion'])
        hit = store(original).search_explained('compassion')[0]
        self.assertIs(hit.entry, original)
        self.assertEqual(hit.score, 1)
        self.assertEqual(hit.field_matches, (('title', ('compassion',)), ('tags[0]', ('compassion',))))
        self.assertFalse(hit.entry.verified)
        self.assertEqual(hit.entry.principle, 'Unrelated passage')

    def test_unicode_and_normalization_are_explained(self):
        hit = store(entry('a', principle='करुणा કરુણા Cafe\u0301')).search_explained('CAFÉ કરુણા करुणा')[0]
        self.assertEqual(hit.score, 3)
        self.assertEqual(hit.matched_terms, tuple(sorted(('café', 'કરુણા', 'करुणा'))))
        self.assertEqual(hit.field_matches, (('principle', hit.matched_terms),))
        self.assertEqual(hit.entry.principle, 'करुणा કરુણા Cafe\u0301')

    def test_order_limits_and_repetition_match_search(self):
        s = store(entry('z', title='alpha beta'), entry('b', title='alpha'), entry('a', title='alpha'))
        for limit in (1, 2, 3):
            hits = s.search_explained('beta alpha alpha', limit)
            self.assertEqual([h.entry for h in hits], s.search('beta alpha alpha', limit))
        self.assertEqual([h.entry.entry_id for h in s.search_explained('alpha beta')], ['z', 'a', 'b'])
        self.assertEqual([h.score for h in s.search_explained('alpha beta')], [2, 1, 1])

    def test_all_searchable_fields_and_tag_indexes(self):
        fields = dict(title='alpha', principle='alpha', guidance='alpha', source='alpha',
                      work='alpha', edition='alpha', location='alpha', tags=['other', 'alpha'])
        hit = store(entry('a', **fields)).search_explained('alpha')[0]
        self.assertEqual([name for name, _ in hit.field_matches],
                         ['title', 'principle', 'guidance', 'source', 'work', 'edition', 'location', 'tags[1]'])
        self.assertEqual(hit.score, 1)

    def test_nonsearchable_metadata_stays_nonsearchable(self):
        self.assertEqual(store(entry('a', language='alpha', license='alpha')).search_explained('alpha'), [])

    def test_no_match_empty_and_substring(self):
        s = store(entry('a', title='apartment'))
        for query in ('', '123', 'art', 'missing'):
            self.assertEqual(s.search_explained(query), [])

    def test_query_and_limit_rejections(self):
        s = store(entry('a'))
        for query in (None, 3, 'a' * 10001):
            with self.assertRaises(ValueError): s.search_explained(query)
        for limit in (0, 101, True, 1.2):
            with self.assertRaises(ValueError): s.search_explained('', limit)

    def test_late_scan_failure_does_not_return_early_hit(self):
        s = store(entry('a', title='alpha'), entry('b', title='other'))
        with patch('jace.retrieval_limits.MAX_SCAN_ROWS', 1):
            with self.assertRaises(ValueError): s.search_explained('alpha', 1)


if __name__ == '__main__': unittest.main()
