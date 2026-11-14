import dataclasses,json,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace._fresh_study import consumer as c
from jace import fresh_study_request as request
class QueueTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def call(self,**kwargs):
        options=dict(operation='review_queue',offset=0,limit=8,reviewed_noncandidates=True)
        options.update(kwargs);return self.f.call(**options)
    def test_metadata_only_pending(self):
        out=self.call();self.assertEqual(out['total_count'],1)
        self.assertNotIn('records',out);self.assertNotIn('Invented',json.dumps(out))
        item=out['review_items'][0];self.assertEqual(item['xml_id'],'SAS_')
        self.assertEqual(item['required_review_domains'],['edition_citation_identity'])
        self.assertEqual(item['status'],'pending');self.assertIsNone(item['reviewer']);self.assertIsNone(item['evidence'])
        self.assertFalse(item['training_admitted']);self.assertFalse(item['scholarly_verified'])
        self.assertFalse(out['reviewer_identity_authenticated']);self.assertTrue(all(v is False for v in out['safety'].values()))
    def test_pagination(self):
        self.assertEqual(self.call(offset=1)['review_items'],[])
        with self.assertRaises(c.ConsumerError):self.call(offset=2)
    def test_opt_in_required_before_io(self):
        with patch.object(c,'_Snapshot',side_effect=AssertionError('unexpected IO')):
            with self.assertRaises(c.ConsumerError):self.call(reviewed_noncandidates=False)
    def test_mixed_options_refused(self):
        for options in [dict(query='x'),dict(category='root_text_label'),dict(xml_id='SAS_'),dict(xml_ids=['a','b']),dict(required_terms=['a']),dict(before=1),dict(limit=9),dict(offset=True)]:
            with self.subTest(options=options),self.assertRaises(c.ConsumerError):self.call(**options)
    def test_quote_and_citation_domains(self):
        record=dict(id='synthetic',source_xml_id=None,source_xml_path='/synthetic',parsed_text_sha256='0'*64,category='quotation_markup',inherited_xml_lang='sa',containing_record_ids=[],citation_status='missing_or_unrecognized_identifier')
        item=c._pending_review_item(record)
        self.assertEqual(len(item['required_review_domains']),4)
        self.assertEqual(item['inherited_language_not_verified'],'sa')
    def test_cli_consent_and_shape(self):
        req=dict(operation='review_queue',offset=0,limit=8,pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study))
        for disclosure,review in [(False,True),(True,False)]:
            with self.assertRaises(c.ConsumerError):request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=disclosure,review_noncandidates=review)
        out=json.loads(request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True,review_noncandidates=True))
        self.assertEqual(out['total_count'],1)
    def test_pin_guard_retained(self):
        with self.assertRaises(c.ConsumerError):
            c.consume(str(self.f.bundle),pins=dataclasses.replace(self.f.pins,source_sha256='0'*64),declaration=self.f.study,operation='review_queue',offset=0,limit=1,reviewed_noncandidates=True)
