import dataclasses,json,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace import fresh_study_request as r
class SelectionTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def call(self,ids,**kw):
  req=dict(operation='select',xml_ids=ids,pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study))
  return json.loads(r.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=kw.pop('disclose',True),**kw))
 def test_order_separate_records(self):
  out=self.call(['SAS_1','TAS_1.1']);self.assertEqual([x['source_xml_id'] for x in out['records']],['SAS_1','TAS_1.1']);self.assertEqual(out['selection_relation'],'explicit_selection_not_inferred_support');self.assertTrue(all(v is False for x in out['records'] for v in x['safety'].values()));self.assertTrue(out['attribution_notice'])
 def test_bad_selection(self):
  for ids in [None,[],['SAS_1'],['SAS_1']*6,['SAS_1','SAS_1'],['SAS_1',True],['SAS_1',''],['SAS_1','x'*257], 'SAS_1']:
   with self.assertRaises(r.ConsumerError):self.call(ids)
 def test_missing_fails_whole_selection(self):
  with self.assertRaises(r.ConsumerError):self.call(['SAS_1','absent'])
 def test_review_gate(self):
  with self.assertRaises(r.ConsumerError):self.call(['SAS_1','note1'])
  out=self.call(['SAS_1','note1'],review_noncandidates=True);self.assertEqual(len(out['records']),2)
 def test_disclosure_required(self):
  with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError):self.call(['SAS_1','SAS_2'],disclose=False)
  consume.assert_not_called()
 def test_complete_output_bound(self):
  with patch.object(r,'MAX_OUTPUT_BYTES',1),self.assertRaises(r.ConsumerError):self.call(['SAS_1','TAS_1.1'])
