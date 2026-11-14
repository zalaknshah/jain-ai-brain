import dataclasses,json,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace import fresh_study_request as r
class LayerTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def call(self,category,review=False,**kw):
  req=dict(operation='browse',offset=0,limit=8,category=category,pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study));req.update(kw)
  return json.loads(r.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True,review_noncandidates=review))
 def test_root_scope(self):
  out=self.call('root_text_label');self.assertEqual(out['total_count'],1);self.assertEqual(out['records'][0]['source_xml_id'],'TAS_1.1');self.assertEqual(out['category_filter'],'root_text_label')
 def test_note_requires_review(self):
  with self.assertRaises(r.ConsumerError):self.call('note_markup')
  out=self.call('note_markup',True);self.assertEqual(out['total_count'],1);self.assertEqual(out['records'][0]['source_xml_id'],'note1')
 def test_offsets_within_filtered_set(self):
  out=self.call('root_text_label',offset=1);self.assertEqual(out['records'],[])
  with self.assertRaises(r.ConsumerError):self.call('root_text_label',offset=2)
 def test_unknown_or_null(self):
  for c in ['root','ROOT_TEXT_LABEL','',None,True,[]]:
   with self.assertRaises(r.ConsumerError):self.call(c)
 def test_review_does_not_admit(self):
  out=self.call('commentary_label',True);self.assertTrue(all(v is False for x in out['records'] for v in x['safety'].values()))
 def test_lookup_rejects_filter(self):
  with self.assertRaises(r.ConsumerError):self.f.call(operation='lookup',xml_id='SAS_1',category='commentary_label')
 def test_search_filters_before_locations(self):
  out=self.f.call(operation='search',query='Invented',limit=8,category='root_text_label');self.assertEqual(out['match_count'],1);self.assertEqual(out['match_locations'][0]['record_id'],out['records'][0]['id'])
