import dataclasses,io,json,sys,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace import cli,fresh_study_request as r

class ContextRequestTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def request(self,**kw):
  value={'operation':'lookup','xml_id':'SAS_1','pins':dataclasses.asdict(self.f.pins),'declaration':dataclasses.asdict(self.f.study)};value.update(kw);return json.dumps(value).encode()
 def call(self,request=None,**kw):
  return json.loads(r.run_request(request or self.request(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True,**kw))
 def test_explicit_context_stays_separate(self):
  page=self.call(self.request(before=1));self.assertEqual([x['source_xml_id'] for x in page['records']],['TAS_1.1','SAS_1']);self.assertEqual(page['context_units_before'],1);self.assertEqual(page['context_units_after'],0);self.assertEqual(page['context_relation'],'adjacent_extracted_units_not_inferred_support')
  self.assertEqual(page['target_record_id'],page['records'][1]['id']);self.assertIn('attribution_notice',page)
 def test_default_remains_single_unit(self):
  self.assertEqual(len(self.call()['records']),1)
 def test_noncandidate_neighbor_requires_review(self):
  with self.assertRaises(r.ConsumerError):self.call(self.request(after=2))
  page=self.call(self.request(after=2),review_noncandidates=True);self.assertEqual([x['source_xml_id'] for x in page['records']],['SAS_1','SAS_2','note1']);self.assertIn(page['records'][1]['id'],page['records'][2]['containing_record_ids']);self.assertTrue(all(v is False for x in page['records'] for v in x['safety'].values()))
 def test_edges_not_silently_shortened(self):
  for kw in [{'xml_id':'TAS_1.1','before':1},{'xml_id':'SAS_3','after':1}]:
   with self.assertRaises(r.ConsumerError):self.call(self.request(**kw))
 def test_bad_counts_before_consumer(self):
  for key in ['before','after']:
   for value in [None,True,-1,9,1.5,'1',[]]:
    with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError):self.call(self.request(**{key:value}))
    consume.assert_not_called()
 def test_other_operations_reject_context(self):
  for req in [{'operation':'inventory','xml_id':None,'before':0},{'operation':'search','query':'Invented','limit':1,'after':0},{'operation':'browse','offset':0,'limit':1,'before':0}]:
   req.update(pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study))
   with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError):self.call(json.dumps(req).encode())
   consume.assert_not_called()
 def test_no_disclosure_still_refused(self):
  with self.assertRaises(r.ConsumerError):r.run_request(self.request(before=1),bundle_directory=str(self.f.bundle),confirmed=True)
 def test_cli_context_without_engine(self):
  args=['jace','fresh-source-study','--stdin','--bundle-directory',str(self.f.bundle),'--confirm-private-study','--allow-local-disclosure']
  stdin=io.TextIOWrapper(io.BytesIO(self.request(before=1)),encoding='utf-8')
  with patch.object(sys,'argv',args),patch.object(sys,'stdin',stdin),patch.object(sys,'stdout',io.StringIO()) as out,patch.object(cli,'CognitiveEngine',side_effect=AssertionError('no engine')) as engine:
   cli.main();self.assertEqual(len(json.loads(out.getvalue())['records']),2);engine.assert_not_called()
