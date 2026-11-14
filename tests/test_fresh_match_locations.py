import unittest
from jace._fresh_study.consumer import _literal_locations
class LocationsTests(unittest.TestCase):
 def record(self,values):
  parts=[dict(text=v,xml_path='/part'+str(i),slot='text',inherited_xml_lang='und',within_note_markup=i==2,within_quotation_markup=i==1) for i,v in enumerate(values)]
  return dict(id='synthetic',parsed_text=''.join(values),parsed_text_parts=parts)
 def test_quote_boundary(self):
  out=_literal_locations(self.record(['alpha ','quoted',' tail']),'a quoted')['locations'][0]
  self.assertEqual((out['start'],out['end']),(4,12));self.assertTrue(out['crosses_part_boundary']);self.assertEqual([p['within_quotation_markup'] for p in out['fragments']],[False,True]);self.assertEqual(out['fragments'][0]['part_start'],4)
 def test_unicode_not_bytes(self):
  out=_literal_locations(self.record(['અ','हिन्दी']),'हिन्दी')['locations'][0];self.assertEqual(out['start'],1);self.assertEqual(out['end'],7)
 def test_overlapping(self):
  out=_literal_locations(self.record(['aaaa']),'aa');self.assertEqual([x['start'] for x in out['locations']],[0,1,2]);self.assertFalse(out['more_locations'])
 def test_cap(self):
  out=_literal_locations(self.record(['a'*40]),'a');self.assertEqual(len(out['locations']),32);self.assertTrue(out['more_locations'])
 def test_exact_cap(self):self.assertFalse(_literal_locations(self.record(['a'*32]),'a')['more_locations'])
 def test_empty_parts_not_fragments(self):
  out=_literal_locations(self.record(['a','','b']),'ab')['locations'][0];self.assertEqual([x['part_index'] for x in out['fragments']],[0,2])
 def test_missing(self):self.assertEqual(_literal_locations(self.record(['abc']),'z')['locations'],[])

class SearchIntegrationTests(unittest.TestCase):
 def test_search_locations_are_selected_page_only(self):
  import test_fresh_package_consumer as fixtures
  f=fixtures.ConsumerTests();f.setUp();self.addCleanup(f.doCleanups)
  out=f.call(operation='search',query='Invented',limit=1,offset=1)
  self.assertEqual(len(out['match_locations']),1);self.assertEqual(out['match_locations'][0]['record_id'],out['records'][0]['id']);self.assertEqual(out['match_locations'][0]['locations'][0]['start'],0)
