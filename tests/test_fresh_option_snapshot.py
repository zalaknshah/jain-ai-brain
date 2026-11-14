import unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace._fresh_study import consumer as c
class OptionOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def mutate_during_open(self, callback):
        original=c._Snapshot.__enter__
        def enter(snapshot):
            callback()
            return original(snapshot)
        return patch.object(c._Snapshot,'__enter__',enter)
    def test_conjunction_does_not_broaden(self):
        terms=['beta']
        with self.mutate_during_open(terms.clear):
            out=self.f.call(operation='search',query='Invented',limit=8,required_terms=terms)
        self.assertEqual([r['source_xml_id'] for r in out['records']],['SAS_1'])
        self.assertEqual(out['required_terms'],['beta'])
        self.assertEqual(terms,[])
    def test_selection_retains_reviewed_order(self):
        ids=['TAS_1.1','SAS_1']
        with self.mutate_during_open(lambda: ids.reverse()):
            out=self.f.call(operation='select',xml_ids=ids)
        self.assertEqual([r['source_xml_id'] for r in out['records']],['TAS_1.1','SAS_1'])
    def test_injected_selection_not_disclosed(self):
        ids=['TAS_1.1','SAS_1']
        with self.mutate_during_open(lambda: ids.append('SAS_3')):
            out=self.f.call(operation='select',xml_ids=ids)
        self.assertEqual(len(out['records']),2)
    def test_additional_term_not_changed(self):
        terms=['beta']
        with self.mutate_during_open(lambda: terms.__setitem__(0,'final')):
            out=self.f.call(operation='search',query='Invented',limit=8,required_terms=terms)
        self.assertEqual(out['required_terms'],['beta'])
        self.assertEqual(out['records'][0]['source_xml_id'],'SAS_1')
    def test_oversize_refused_before_io(self):
        with patch.object(c, '_Snapshot', side_effect=AssertionError('unexpected IO')):
            for options in [dict(operation='select',xml_ids=['x']*10000),
                            dict(operation='search',query='q',limit=1,required_terms=['x']*10000)]:
                with self.assertRaises(c.ConsumerError):self.f.call(**options)
    def test_empty_lists_still_refused(self):
        for options in [dict(operation='select',xml_ids=[]),
                        dict(operation='search',query='q',limit=1,required_terms=[])]:
            with self.assertRaises(c.ConsumerError):self.f.call(**options)
