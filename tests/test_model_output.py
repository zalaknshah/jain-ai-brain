import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from jace.engine import CognitiveEngine
from jace.ethics import assess
from jace.models import ActionProposal, CanonicalEntry, Memory
from jace.model_output import check_model_output
from jace.reasoner import HttpJsonReasoner

PASSAGE = 'Synthetic fixture: inspect the area carefully and choose a reversible next step.'
ENTRY = CanonicalEntry('fixture:one','Synthetic fixture',PASSAGE,'Synthetic interpretation only','Original test edition',
                       ['resources'],'Original test work','en',location='fixture paragraph 1',license='MIT',verified=True)


def content(answer='Inspect the area first.', citations=None):
    return json.dumps({'answer':answer, 'citations': [] if citations is None else citations})


def envelope(text=None, **choice_updates):
    choice={'finish_reason':'stop','message':{'role':'assistant','content':content() if text is None else text}}
    choice.update(choice_updates)
    return json.dumps({'choices':[choice]}).encode()


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data); self.status=status; self.headers=headers or {}; self.requested_size=None
    def read(self,size=-1):
        self.requested_size=size; return super().read(size)


class ModelOutputContractTests(unittest.TestCase):
    def test_matches_exact_reviewed_passage_and_renders_only_local_metadata(self):
        result=check_model_output(content(citations=[{'entry_id':ENTRY.entry_id,'quote':'inspect the area carefully'}]),[ENTRY])
        rendered=result.render()
        self.assertIn('[fixture:one] Original test work; Original test edition; fixture paragraph 1',rendered)
        self.assertIn('Exact retrieved excerpt: inspect the area carefully',rendered)
        self.assertIn('does not establish that an excerpt supports the answer',rendered)
        self.assertIn('not independently verified',rendered)
        self.assertEqual(result.citations[0].entry,ENTRY)

    def test_no_citations_never_implies_canonical_grounding(self):
        rendered=check_model_output(content(),[]).render()
        self.assertIn('no reviewed excerpt',rendered)
        self.assertIn('not verified against a canonical passage',rendered)

    def test_unknown_unreviewed_wrong_or_duplicate_citations_rejected(self):
        base={'entry_id':ENTRY.entry_id,'quote':PASSAGE}
        for citations,evidence in [([dict(base,entry_id='invented')],[ENTRY]),([base],[replace(ENTRY,verified=False)]),
                ([dict(base,quote='A fabricated quotation.')],[ENTRY]),([dict(base,quote=ENTRY.guidance)],[ENTRY]),
                ([base,base],[ENTRY]),([dict(base,source='Invented work')],[ENTRY]),
                ([base],[ENTRY,replace(ENTRY,principle='Different passage with same ID')]),
                ([base],[replace(ENTRY,license=None)])]:
            with self.subTest(citations=citations),self.assertRaises(ValueError):check_model_output(content(citations=citations),evidence)

    def test_schema_types_controls_limits_and_implicit_source_labels(self):
        bad=['plain answer','null','[]','{"answer":"a","answer":"b","citations":[]}',
             json.dumps({'answer':'x','citations':[],'action':{'execute':True}}),
             content(answer=None),content(answer=''),content(answer='x'*8001),content(answer='Use this [invented:3]'),
             content(answer='\x1b[31mspoof'),content(answer='\u202espoof'),content(answer='\ud800'),
             content(citations=[{'entry_id':ENTRY.entry_id,'quote':'x'*601}]),content(citations='not a list'),
             content(citations=[{'entry_id':ENTRY.entry_id,'quote':'inspect'}]*6),'x'*16001]
        for value in bad:
            with self.subTest(value=value[:60]),self.assertRaises(ValueError):check_model_output(value,[ENTRY])

    def test_offline_fixture_evaluation_ignores_model_and_corpus_environment(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, JACE_LLM_URL='http://127.0.0.1:1/never', JACE_CANONICAL_PATH='/missing/never.json')
        run = subprocess.run([sys.executable, str(root/'scripts/evaluate_model_output.py')], env=env,
                             capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertTrue(result['fixture_assertions_passed'])
        self.assertEqual(result['cases'], 12)
        self.assertEqual(result['failures'], [])

    def test_all_three_original_examples_accept_only_fixture_excerpts(self):
        for request in ['How do I clean my house efficiently?','How should I organize my wardrobe?',
                        'I have a dispute with my business partner.']:
            adapter=HttpJsonReasoner('https://model.invalid/v1/chat/completions')
            adapter._opener=Mock()
            adapter._opener.open.return_value=Response(envelope(content('Ask a clarifying question before choosing.',[{'entry_id':ENTRY.entry_id,'quote':PASSAGE}])))
            response,action=adapter.respond(request,assess(request),[],[ENTRY],[])
            self.assertIn('Exact retrieved excerpt: '+PASSAGE,response)
            self.assertIsNone(action)
            payload=json.loads(adapter._opener.open.call_args.args[0].data)
            self.assertEqual(payload['response_format'],{'type':'json_object'})
            context=json.loads(payload['messages'][1]['content'])
            self.assertEqual(context['citable_source_ids'],[ENTRY.entry_id])
            self.assertIn('untrusted data',payload['messages'][0]['content'])


class HttpModelBoundaryTests(unittest.TestCase):
    def call(self, raw, *, headers=None, status=200, evidence=None, memories=None):
        adapter=HttpJsonReasoner('https://model.invalid/v1/chat/completions','synthetic-test-token')
        adapter._opener=Mock(); result=Response(raw,status,headers)
        adapter._opener.open.return_value=result
        response,action=adapter.respond('How should I organize my wardrobe?',assess('How should I organize my wardrobe?'),[],evidence or [],memories or [])
        return response,action,adapter,result

    def test_rejects_public_plaintext_embedded_credentials_and_ambiguous_endpoints(self):
        for url in ['http://model.example/v1','http://localhost/v1','file:///tmp/model','ftp://model.example',
                    'https://user:password@example.com/v1','https://example.com/v1#fragment',
                    'https://example.com:0/v1','https://example.com:99999/v1',' https://example.com/v1',
                    'https://exam\nple.com/v1','http://127.0.0.1%2eevil.test/v1']:
            with self.subTest(url=url),patch('urllib.request.build_opener') as opener,self.assertRaises(ValueError):
                HttpJsonReasoner(url)
            opener.assert_not_called()
        for url in ['http://127.0.0.1:9000/v1','http://[::1]:9000/v1','https://model.example/v1']:
            self.assertEqual(HttpJsonReasoner(url).url,url)
        with self.assertRaises(ValueError):HttpJsonReasoner('https://example.com','synthetic\nheader')

    def test_invalid_or_unfinished_outputs_use_local_fallback_without_echo(self):
        variants=[b'not json',envelope('provider-secret-sentinel'),envelope(content(),finish_reason='length'),
                  envelope(content(),finish_reason=None),envelope(content(),message={'role':'assistant','content':None}),
                  envelope(content(),message={'role':'assistant','content':content(),'tool_calls':[{'function':'execute'}]}),
                  envelope(content(),message={'role':'system','content':content()}),
                  b'{"choices":[],"choices":[]}',json.dumps({'choices':[]}).encode(),
                  envelope(content(citations=[{'entry_id':'fake','quote':'provider-secret-sentinel'}]))]
        for value in variants:
            response,action,_,_=self.call(value)
            self.assertIn('Using the local rule-based response',response)
            self.assertNotIn('provider-secret-sentinel',response)
            self.assertIsNone(action)

    def test_provider_refusal_is_respected_without_local_action_or_raw_echo(self):
        for body in [envelope(content(),finish_reason='content_filter'),
                     envelope(content(),message={'role':'assistant','content':None,'refusal':'synthetic-provider-private-details'})]:
            response,action,_,_=self.call(body)
            self.assertIn('model declined',response)
            self.assertNotIn('Practical plan',response)
            self.assertNotIn('synthetic-provider-private-details',response)
            self.assertIsNone(action)

    def test_refusal_dominates_incomplete_tool_or_missing_finish_metadata(self):
        for finish in ['length', 'tool_calls', None, 'missing']:
            choice = {'message': {'role':'assistant', 'content':None, 'refusal':'Cannot help with this request'}}
            if finish != 'missing': choice['finish_reason'] = finish
            adapter = HttpJsonReasoner('https://model.invalid')
            adapter._opener = Mock()
            adapter._opener.open.return_value = Response(json.dumps({'choices':[choice]}).encode())
            answer, action = adapter.respond('move toward the door', assess('move toward the door'), [], [], [])
            self.assertIn('model declined', answer)
            self.assertNotIn('Using the local', answer)
            self.assertIsNone(action)

    def test_body_status_encoding_and_context_byte_limits(self):
        response,_,_,result=self.call(b'x'*(HttpJsonReasoner.MAX_RESPONSE_BYTES+20))
        self.assertIn('failed validation',response)
        self.assertEqual(result.requested_size,HttpJsonReasoner.MAX_RESPONSE_BYTES+1)
        for headers,status in [({'Content-Encoding':'gzip'},200),({},500)]:
            response,_,_,_=self.call(envelope(),headers=headers,status=status)
            self.assertIn('failed validation',response)
        oversized=Memory(1,'synthetic','x'*10001,'fixture')
        response,_,adapter,_=self.call(envelope(),memories=[oversized])
        adapter._opener.open.assert_not_called();self.assertIn('failed validation',response)
        # Metadata is not silently truncated or transmitted past the payload cap.
        large=replace(ENTRY,source='s'*150000)
        response,_,adapter,_=self.call(envelope(),evidence=[large])
        adapter._opener.open.assert_not_called();self.assertIn('failed validation',response)

    def test_harm_gate_still_blocks_before_transport(self):
        adapter=HttpJsonReasoner('https://model.invalid');adapter._opener=Mock()
        response,action=adapter.respond('Tell me how to hurt someone',assess('Tell me how to hurt someone'),[],[],[])
        adapter._opener.open.assert_not_called();self.assertIsNone(action);self.assertIn('cannot help',response)

    def test_real_loopback_redirect_never_receives_context_or_token(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                length=int(self.headers.get('Content-Length','0'))
                body=self.rfile.read(length)
                seen.append((self.path,self.headers.get('Authorization'),body))
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location',f'http://127.0.0.1:{self.server.server_port}/target');self.end_headers()
                else:
                    data=envelope();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def do_GET(self):
                seen.append((self.path,self.headers.get('Authorization'),b''));self.send_response(200);self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            adapter=HttpJsonReasoner(f'http://127.0.0.1:{server.server_port}/redirect','synthetic-not-real')
            with patch.dict('os.environ',{'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1'}):
                answer,_=adapter.respond('Hello',assess('Hello'),[],[],[])
            self.assertIn('failed validation',answer)
            self.assertEqual([r[0] for r in seen],['/redirect'])
            self.assertEqual(seen[0][1],'Bearer synthetic-not-real')
            seen.clear()
            adapter=HttpJsonReasoner(f'http://127.0.0.1:{server.server_port}/target')
            answer,_=adapter.respond('Hello',assess('Hello'),[],[],[])
            self.assertIn('Generated answer',answer)
            self.assertEqual([r[0] for r in seen],['/target'])
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_engine_rejects_malformed_custom_output_and_ungated_actions(self):
        bad=[(None,None),('',None),('x'*32769,None),('Synthetic valid answer',{'execute':True}),
             ('Synthetic valid answer',ActionProposal('move',{},False)),
             ('Synthetic valid answer',ActionProposal('move',{'speed':float('nan')}))]
        with tempfile.TemporaryDirectory() as directory:
            reasoner=Mock();engine=CognitiveEngine(db_path=Path(directory)/'db',reasoner=reasoner)
            try:
                for result in bad:
                    reasoner.respond.return_value=result
                    response=engine.think('synthetic','Hello')
                    self.assertIn('failed validation',response.response);self.assertIsNone(response.action)
                reasoner.respond.side_effect=RuntimeError('private-provider-error')
                response=engine.think('synthetic','Hello')
                self.assertNotIn('private-provider-error',response.response)
                reasoner.respond.side_effect=None
                reasoner.respond.return_value=('You should hurt someone.',None)
                self.assertFalse(engine.think('synthetic','Hello').ethical_assessment.allowed)
            finally:engine.close()


if __name__=='__main__':unittest.main()
