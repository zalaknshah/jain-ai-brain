import hashlib
import unittest
from scripts.locate_tei_terms import locate


def xml(body):
    return ('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><lg n="ignored">term</lg></teiHeader><text xml:lang="pra-Latn"><body>' + body + '</body></text></TEI>').encode()


def search(data, query='term', **kwargs):
    return locate(data, hashlib.sha256(data).hexdigest(), query, **kwargs)


class TermLocatorTests(unittest.TestCase):
    def test_metadata_only_and_body_scope(self):
        result = search(xml('<lg n="7"><l>term</l><l>term</l></lg>'))
        self.assertEqual(result['groups_examined'], 1)
        self.assertEqual(result['matches'][0]['character_offsets'], [0, 4])
        self.assertNotIn('declared_language', result['matches'][0])
        self.assertNotIn('parsed_text', result['matches'][0])
        self.assertFalse(result['translation_verified'])
        self.assertFalse(result['training_admitted'])

    def test_literal_not_word_or_normalized(self):
        data = xml('<lg>aaaa ā ā Term</lg>')
        self.assertEqual(search(data, 'aa')['matches'][0]['character_offsets'], [0, 1, 2])
        self.assertEqual(search(data, 'ā')['matches'][0]['character_offsets'], [5])
        self.assertEqual(search(data, 'term')['matching_groups'], 0)

    def test_limit_and_duplicate_number(self):
        result = search(xml('<lg n="1">term</lg><lg n="1" xml:lang="san-Latn">term</lg>'), limit=1)
        self.assertEqual(result['matching_groups'], 2)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['matches'][0]['group_index'], 1)

    def test_entities_are_parsed_but_doctype_rejected(self):
        self.assertEqual(search(xml('<lg>t&#101;rm</lg>'))['matching_groups'], 1)
        with self.assertRaises(ValueError):
            search(b'<!DOCTYPE TEI [<!ENTITY x "term">]>' + xml('<lg>&x;</lg>'))

    def test_fail_closed(self):
        data = xml('<lg>term</lg>')
        for kwargs in ({'limit': True}, {'limit': 0}, {'limit': 101}):
            with self.assertRaises(ValueError): search(data, **kwargs)
        for query in ('', ' ', 'x'*129):
            with self.assertRaises(ValueError): search(data, query)
        with self.assertRaises(ValueError): locate(data, '0'*64, 'term')
        with self.assertRaises(ValueError): search(b'<TEI/>')
        with self.assertRaises(ValueError): search(b'\x00')
        with self.assertRaises(ValueError): search(b'x' * (2*1024*1024+1))

    def test_depth_and_language_override(self):
        with self.assertRaises(ValueError): search(xml('<div>'*130+'<lg>term</lg>'+'</div>'*130))
        result = search(xml('<lg xml:lang="san-Latn">term</lg>'))
        self.assertNotIn('declared_language', result['matches'][0])

    def test_adversarial_offsets_bounded(self):
        result = search(xml('<lg>' + 'a'*200000 + '</lg>'), 'a')
        self.assertEqual(len(result['matches'][0]['character_offsets']), 64)
        self.assertTrue(result['matches'][0]['offsets_truncated'])
        result = search(xml(('<lg>'+'a'*1000+'</lg>')*12), 'a')
        self.assertEqual(sum(len(m['character_offsets']) for m in result['matches']), 512)
        self.assertEqual(result['matches'][8]['character_offsets'], [])
        self.assertTrue(result['matches'][8]['offsets_truncated'])
        limited = search(xml(('<lg>'+'a'*1000+'</lg>')*12), 'a', limit=1)
        self.assertEqual(limited['matching_groups'], 12)
        self.assertEqual(len(limited['matches']), 1)
        self.assertEqual(len(limited['matches'][0]['character_offsets']), 64)

    def test_source_attributes_and_query_never_echoed(self):
        import json
        data = xml('<lg n="SECRET SOURCE PROSE" xml:lang="MORE SECRET PROSE">privatephrase</lg>')
        result = search(data, 'privatephrase')
        output = json.dumps(result)
        for secret in ('SECRET', 'PROSE', 'privatephrase'):
            self.assertNotIn(secret, output)
        self.assertEqual(result['query_sha256'], hashlib.sha256(b'privatephrase').hexdigest())
        self.assertEqual(set(result['matches'][0]), {'group_index', 'parsed_text_sha256', 'character_offsets', 'offsets_truncated'})

if __name__ == '__main__': unittest.main()
