import dataclasses,json,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace._fresh_study import consumer as c
from jace import fresh_study_request as r

class BrowseTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def call(self,offset=0,limit=2,**kw):
  return c.consume(str(self.f.bundle),pins=self.f.pins,declaration=self.f.study,operation='browse',offset=offset,limit=limit,**kw)
 def test_complete_candidate_pagination(self):
  first=self.call();second=self.call(offset=first['next_offset'])
  records=first['records']+second['records']
  self.assertEqual([x['source_xml_id'] for x in records],['TAS_1.1','SAS_1','SAS_3']);self.assertEqual(first['total_count'],3);self.assertTrue(first['truncated']);self.assertFalse(second['truncated']);self.assertIsNone(second['next_offset'])
  self.assertNotIn('match_count',first);self.assertNotIn('matching',first)
 def test_review_scope_complete_and_overlap_preserved(self):
  offset=0;records=[]
  while offset is not None:
   page=self.call(offset=offset,limit=1,reviewed_noncandidates=True);records+=page['records'];offset=page['next_offset']
  self.assertEqual(len(records),6);self.assertEqual(len({x['id'] for x in records}),6)
  self.assertEqual([x['source_xml_id'] for x in records],['TAS_1.1','SAS_1','SAS_2','note1','SAS_','SAS_3'])
  self.assertIn(records[2]['id'],records[3]['containing_record_ids']);self.assertEqual(page['search_scope'],'all_selected_units')
  self.assertTrue(all(x is False for record in records for x in record['safety'].values()))
 def test_end_offset_empty_not_truncated(self):
  page=self.call(offset=3);self.assertEqual(page['records'],[]);self.assertIsNone(page['next_offset']);self.assertFalse(page['truncated'])
  with self.assertRaises(c.ConsumerError):self.call(offset=4)
 def test_invalid_bounds_before_io(self):
  for offset,limit in [(None,2),(-1,2),(True,2),(1.5,2),(5001,2),(0,None),(0,True),(0,0),(0,9)]:
   with self.subTest(offset=offset,limit=limit),patch.object(c,'_Snapshot') as snapshot,self.assertRaises(c.ConsumerError):self.call(offset,limit)
   snapshot.assert_not_called()
 def test_wrong_options(self):
  for kw in [{'query':'x'},{'xml_id':'SAS_1'},{'before':1},{'after':1}]:
   with self.assertRaises(c.ConsumerError):self.call(**kw)
 def test_search_later_page(self):
  page=c.consume(str(self.f.bundle),pins=self.f.pins,declaration=self.f.study,operation='search',query='Invented',limit=1,offset=2)
  self.assertEqual(page['records'][0]['source_xml_id'],'SAS_3');self.assertEqual(page['match_count'],3);self.assertEqual(page['total_count'],3);self.assertIsNone(page['next_offset'])
 def test_wrong_pin_no_page(self):
  with self.assertRaises(c.ConsumerError):c.consume(str(self.f.bundle),pins=dataclasses.replace(self.f.pins,records_sha256='0'*64),declaration=self.f.study,operation='browse',offset=0,limit=1)
 def request(self,**kw):
  value={'operation':'browse','offset':0,'limit':2,'pins':dataclasses.asdict(self.f.pins),'declaration':dataclasses.asdict(self.f.study)};value.update(kw);return json.dumps(value).encode()
 def test_cli_adapter_disclosure_and_scope(self):
  with self.assertRaises(r.ConsumerError):r.run_request(self.request(),bundle_directory=str(self.f.bundle),confirmed=True)
  page=json.loads(r.run_request(self.request(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True));self.assertEqual(page['next_offset'],2);self.assertIn('attribution_notice',page)
 def test_adapter_exact_fields_and_null_offset(self):
  for kw in [{'xml_id':None},{'query':'x'},{'offset':None},{'offset':False}]:
   with self.assertRaises(r.ConsumerError):r.run_request(self.request(**kw),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True)
 def test_other_operations_reject_offset(self):
  with self.assertRaises(c.ConsumerError):c.consume(str(self.f.bundle),pins=self.f.pins,declaration=self.f.study,offset=0)
