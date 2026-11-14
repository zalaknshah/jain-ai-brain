import dataclasses
import io
import json
import sys
import unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace import cli
from jace import fresh_study_request as r

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ConsumerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.req={'operation':'inventory','xml_id':None,'pins':dataclasses.asdict(self.f.pins),'declaration':dataclasses.asdict(self.f.study)}
    def raw(self): return json.dumps(self.req).encode()
    def call(self,**kw): return r.run_request(self.raw(),bundle_directory=str(self.f.bundle),confirmed=True,**kw)
    def test_inventory(self):
        out=self.call(); self.assertNotIn('Invented',out); self.assertNotIn('records',json.loads(out)); self.assertTrue(all(x is False for x in json.loads(out)['safety'].values()))
    def test_lookup_disclosure(self):
        self.req.update(operation='lookup',xml_id='SAS_1')
        with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError): self.call()
        consume.assert_not_called()
        out=json.loads(self.call(allow_local_disclosure=True));self.assertEqual(out['records'][0]['parsed_text'],'Invented beta detail.');self.assertIn('attribution_notice',out)
    def test_noncandidate_review(self):
        self.req.update(operation='lookup',xml_id='SAS_2')
        with self.assertRaises(r.ConsumerError): self.call(allow_local_disclosure=True)
        out=json.loads(self.call(allow_local_disclosure=True,review_noncandidates=True));self.assertFalse(out['records'][0]['candidate_for_literal_study']);self.assertTrue(all(x is False for x in out['records'][0]['safety'].values()))
    def test_inventory_switches(self):
        for kw in ({'allow_local_disclosure':True},{'review_noncandidates':True}):
            with self.assertRaises(r.ConsumerError): self.call(**kw)
    def test_confirmation(self):
        with patch.object(r,'consume') as consume:
            for confirmed in (False,1,None):
                with self.assertRaises(r.ConsumerError): r.run_request(self.raw(),bundle_directory='/no-open',confirmed=confirmed)
            consume.assert_not_called()
    def test_bad_requests(self):
        for raw in (b'',b'[]',b'{"operation":1,"operation":2}',b'NaN',b'x'*8193,b'\xff'):
            with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError): r.run_request(raw,bundle_directory='/no-open',confirmed=True)
            consume.assert_not_called()
        for field,value in (('pins',{}),('declaration',{}),('operation',[]),('operation','train'),('xml_id','unexpected'),('extra',True)):
            req=dict(self.req);req[field]=value
            with patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError): r.run_request(json.dumps(req).encode(),bundle_directory='/no-open',confirmed=True)
            consume.assert_not_called()
    def test_bound(self):
        with patch.object(r,'MAX_OUTPUT_BYTES',1),self.assertRaises(r.ConsumerError): self.call()
    def test_bad_hash(self):
        self.req['pins']['records_sha256']='0'*64
        with self.assertRaises(r.ConsumerError): self.call()
    def test_platform(self):
        with patch.object(r.os,'name','nt'),patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError): self.call()
        consume.assert_not_called()
    def test_cli_inventory(self):
        args=['jace','fresh-source-study','--stdin','--bundle-directory',str(self.f.bundle),'--confirm-private-study']
        stdin=io.TextIOWrapper(io.BytesIO(self.raw()),encoding='utf-8')
        with patch.object(sys,'argv',args),patch.object(sys,'stdin',stdin),patch.object(sys,'stdout',io.StringIO()) as out,patch.object(cli,'CognitiveEngine',side_effect=AssertionError('no engine')) as engine:
            cli.main();self.assertEqual(json.loads(out.getvalue())['operation'],'inventory');engine.assert_not_called()
    def test_cli_denied_no_output(self):
        self.req.update(operation='lookup',xml_id='SAS_1')
        args=['jace','fresh-source-study','--stdin','--bundle-directory',str(self.f.bundle),'--confirm-private-study']
        stdin=io.TextIOWrapper(io.BytesIO(self.raw()),encoding='utf-8')
        with patch.object(sys,'argv',args),patch.object(sys,'stdin',stdin),patch.object(sys,'stdout',io.StringIO()) as out,patch.object(sys,'stderr',io.StringIO()) as err,self.assertRaises(SystemExit) as exited:
            cli.main()
        self.assertEqual(exited.exception.code,2);self.assertEqual(out.getvalue(),'');self.assertNotIn('Invented',err.getvalue());self.assertNotIn(str(self.f.bundle),err.getvalue())

    def test_descriptor_capability_refusal(self):
        with patch.object(r.os,'supports_dir_fd',set()),patch.object(r,'consume') as consume,self.assertRaises(r.ConsumerError): self.call()
        consume.assert_not_called()
    def test_controls_serialized_not_rendered(self):
        with patch.object(r,'consume',return_value={'fictional':'\x1b[31m\u202e'}):
            wire=self.call()
        self.assertNotIn('\x1b',wire);self.assertNotIn('\u202e',wire)
        self.assertEqual(json.loads(wire)['fictional'],'\x1b[31m\u202e')
