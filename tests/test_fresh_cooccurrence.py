import dataclasses
import json
import unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace import fresh_study_request as request
from jace._fresh_study import consumer

class CooccurrenceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ConsumerTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
    def call(self, terms, **kwargs):
        options = dict(operation='search', query='Invented', limit=8, required_terms=terms)
        options.update(kwargs)
        return self.f.call(**options)
    def test_all_terms_same_record(self):
        out = self.call(['beta', 'detail'])
        self.assertEqual([r['source_xml_id'] for r in out['records']], ['SAS_1'])
        self.assertEqual(out['term_relation'], 'same_extracted_record_not_semantic_relationship')
        self.assertEqual(self.call(['alpha', 'beta'])['match_count'], 0)
    def test_locations_labelled_separately(self):
        out = self.call(['beta', 'detail'])
        text = out['records'][0]['parsed_text']
        for group in out['required_term_locations']:
            hit = group['matches'][0]
            self.assertEqual(hit['record_id'], out['records'][0]['id'])
            for loc in hit['locations']:
                self.assertEqual(text[loc['start']:loc['end']], group['term'])
    def test_exact_case_no_normalization(self):
        self.assertEqual(self.call(['Beta'])['match_count'], 0)
        self.assertEqual(self.call(['eta'])['match_count'], 1)
    def test_pagination_after_conjunction(self):
        out = self.call(['beta'], offset=1)
        self.assertEqual(out['records'], [])
        self.assertEqual(out['required_term_locations'][0]['matches'], [])
        with self.assertRaises(consumer.ConsumerError):
            self.call(['beta'], offset=2)
    def test_gate_and_category_remain(self):
        self.assertEqual(self.call(['note'])['match_count'], 0)
        out = self.call(['note'], reviewed_noncandidates=True, category='note_markup')
        self.assertEqual(len(out['records']), 1)
        self.assertTrue(all(value is False for value in out['records'][0]['safety'].values()))
        with self.assertRaises(consumer.ConsumerError):
            self.call(['note'], category='note_markup')
    def test_invalid_before_io(self):
        for terms in [[], 'beta', ['beta']*2, ['Invented'], ['a','b','c','d','e'], [None], [True], [' '], ['\n'], ['\ud800'], ['a'*129]]:
            with self.subTest(terms=terms), patch.object(consumer, '_Snapshot', side_effect=AssertionError('unexpected IO')):
                with self.assertRaises(consumer.ConsumerError):
                    self.call(terms)
    def test_nonsearch_refuses(self):
        with self.assertRaises(consumer.ConsumerError):
            self.f.call(operation='inventory', required_terms=['beta'])
    def test_request_null_and_consent(self):
        req = dict(operation='search', query='Invented',limit=8,required_terms=None,
            pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study))
        for terms, disclosure in [(None,True),(['beta'],False)]:
            req['required_terms']=terms
            with self.assertRaises(consumer.ConsumerError):
                request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=disclosure)
        req['required_terms']=['beta']
        out=json.loads(request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True))
        self.assertEqual(out['match_count'],1)
