import dataclasses
import io
import json
import sys
import unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace._fresh_study import consumer as c
from jace import fresh_study_request as r, cli

class LiteralSearchTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def call(self,query='Invented',limit=2,**kw):
  return c.consume(str(self.f.bundle),pins=self.f.pins,declaration=self.f.study,operation='search',query=query,limit=limit,**kw)
 def request(self,**kw):
  req={'operation':'search','query':'Invented','limit':2,'pins':dataclasses.asdict(self.f.pins),'declaration':dataclasses.asdict(self.f.study)};req.update(kw);return json.dumps(req).encode()
 def test_exact_candidate_results(self):
  out=self.call();self.assertEqual([x['source_xml_id'] for x in out['records']],['TAS_1.1','SAS_1']);self.assertEqual(out['match_count'],3);self.assertTrue(out['truncated']);self.assertEqual(out['search_scope'],'literal_candidates_only')
  self.assertTrue(all(x['candidate_for_literal_study'] for x in out['records']));self.assertIn('attribution_notice',out)
  self.assertTrue(all(v is False for x in out['records'] for v in x['safety'].values()))
 def test_exact_case_no_fuzzy_match(self):
  self.assertEqual(self.call('invented')['records'],[]);self.assertEqual(self.call('Beta')['records'],[])
  self.assertEqual(self.call('beta detail.')['records'][0]['source_xml_id'],'SAS_1')
 def test_default_excludes_note_and_overlapping_parent(self):
  self.assertEqual(self.call('note')['match_count'],0)
  out=self.call('note',8,reviewed_noncandidates=True);self.assertEqual(out['match_count'],2);self.assertEqual(out['search_scope'],'all_selected_units');self.assertEqual([x['source_xml_id'] for x in out['records']],['SAS_2','note1'])
  self.assertIn(out['records'][0]['id'],out['records'][1]['containing_record_ids'])
 def test_limit_and_order(self):
  out=self.call(limit=8);self.assertFalse(out['truncated']);self.assertEqual(len(out['records']),3)
  self.assertEqual(self.call(limit=1)['records'],out['records'][:1])
 def test_invalid_query_and_limit_before_read(self):
  for query,limit in [('',2),(' '*4,2),('x'*129,2),('\x1b',2),('\ud800',2),(None,2),('x',True),('x',0),('x',9),('x',1.0)]:
   with self.subTest(query=repr(query),limit=limit),patch.object(c,'_Snapshot') as snapshot,self.assertRaises(c.ConsumerError):self.call(query,limit)
   snapshot.assert_not_called()
 def test_no_context_or_lookup_options(self):
  for kw in [{'xml_id':'SAS_1'},{'before':1},{'after':1}]:
   with self.assertRaises(c.ConsumerError):self.call(**kw)
 def test_search_args_not_accepted_for_other_operations(self):
  for op in ['inventory','lookup']:
   with self.assertRaises(c.ConsumerError):c.consume(str(self.f.bundle),pins=self.f.pins,declaration=self.f.study,operation=op,xml_id='SAS_1' if op=='lookup' else None,query='x',limit=1)
 def test_wrong_pin_still_rejected(self):
  with self.assertRaises(c.ConsumerError):c.consume(str(self.f.bundle),pins=dataclasses.replace(self.f.pins,records_sha256='0'*64),declaration=self.f.study,operation='search',query='Invented',limit=1)
 def test_request_needs_disclosure(self):
  with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError):r.run_request(self.request(),bundle_directory=str(self.f.bundle),confirmed=True)
  consume.assert_not_called()
  out=json.loads(r.run_request(self.request(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True));self.assertEqual(out['match_count'],3)
 def test_request_shape(self):
  for kw in [{'xml_id':None},{'limit':False},{'query':[]},{'query':'x'*129}]:
   with self.assertRaises(r.ConsumerError):r.run_request(self.request(**kw),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True)
 def test_cli_search_no_engine(self):
  args=['jace','fresh-source-study','--stdin','--bundle-directory',str(self.f.bundle),'--confirm-private-study','--allow-local-disclosure']
  stdin=io.TextIOWrapper(io.BytesIO(self.request()),encoding='utf-8')
  with patch.object(sys,'argv',args),patch.object(sys,'stdin',stdin),patch.object(sys,'stdout',io.StringIO()) as out,patch.object(cli,'CognitiveEngine',side_effect=AssertionError('no engine')) as engine:
   cli.main();self.assertEqual(json.loads(out.getvalue())['match_count'],3);engine.assert_not_called()
 def test_unicode_is_not_normalized(self):
  source='<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/><text><body><p xml:id="TAS_1.1">Invented café અહિંસા</p></body></text></TEI>'.encode()
  f=fixtures.ConsumerTests()
  with patch.object(fixtures,'SOURCE',source):f.setUp()
  self.addCleanup(f.doCleanups)
  def find(query):return c.consume(str(f.bundle),pins=f.pins,declaration=f.study,operation='search',query=query,limit=1)['match_count']
  self.assertEqual(find('café'),1);self.assertEqual(find('cafe\u0301'),0);self.assertEqual(find('અહિંસા'),1)
