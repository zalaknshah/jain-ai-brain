"""Original fictional inputs only; no partner contact, provider or saved case data."""
from copy import deepcopy
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jace.api import JaceHTTPServer
from jace.auth import ApiAuthorization
from jace.dispute import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, parse_worksheet, prepare_dispute, validate_worksheet
from jace.engine import CognitiveEngine

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'synthetic-dispute-token-' + 'x' * 32


def example():
    return json.loads((ROOT/'examples/dispute_worksheet.json').read_text())


class DisputeBuilderTests(unittest.TestCase):
    def test_declared_inputs_affect_comparison_without_verdict_or_inference(self):
        original=example(); result=prepare_dispute(original)
        self.assertEqual(result['worksheet'],original)
        self.assertEqual(result['status'],'preparation_only')
        self.assertIsNone(result['recommended_option']);self.assertIsNone(result['action'])
        for field in ('actions_executed','saved','provider_called','facts_independently_verified','partner_position_verified'):
            self.assertIs(result[field],False)
        changed=deepcopy(original);changed['decision']='Compare fictional working hours.'
        changed['options'][0]['my_fit']='no'
        different=prepare_dispute(changed)
        self.assertNotEqual(result['worksheet']['decision'],different['worksheet']['decision'])
        self.assertNotEqual(result['option_comparisons'][0]['review_prompts'],different['option_comparisons'][0]['review_prompts'])
        self.assertEqual(result['option_comparisons'][1],different['option_comparisons'][1])
        self.assertEqual(original,example())
        result['worksheet']['options'][0]['open_questions'].append('Mutating the result does not change input.')
        self.assertEqual(original,example())

    def test_disputed_and_reported_agreed_labels_remain_user_reports(self):
        value=example();value['options'][0]['agreement']='reported_agreed'
        result=prepare_dispute(value)
        self.assertEqual(result['worksheet']['facts'],value['facts'])
        self.assertEqual(result['declaration_source'],'user_reported')
        self.assertEqual(result['option_comparisons'][0]['declaration_source'],'user_reported')
        self.assertIn('not verified agreement or authorization',' '.join(result['option_comparisons'][0]['review_prompts']))
        self.assertIsNone(result['recommended_option'])

    def test_unknown_positions_and_fit_are_not_filled_in(self):
        value=example();value['my_position']=None;value['partner_position_reported']=None
        for option in value['options']:
            option['my_fit']=option['reported_partner_fit']='unknown'
        value['facts']['reported_agreed']=[]
        result=prepare_dispute(value)
        self.assertIsNone(result['worksheet']['my_position'])
        self.assertIsNone(result['worksheet']['partner_position_reported'])
        self.assertTrue(any('remains unknown' in item for item in result['clarifying_questions']))
        self.assertTrue(any('No agreed facts' in item for item in result['clarifying_questions']))
        value['options'][0]['reported_partner_fit']='yes'
        with self.assertRaises(ValueError):prepare_dispute(value)

    def test_each_constraint_combination_suppresses_trial_recommendation(self):
        for flags in itertools.product((False,True),repeat=3):
            value=example();value['constraints']=dict(zip(('safety_concern','formal_deadline','binding_commitment'),flags))
            value['options'][0]['reversibility']='yes';value['options'][0]['agreement']='reported_agreed'
            with self.subTest(flags=flags):
                result=prepare_dispute(value)
                self.assertEqual(result['status'],'qualified_review_needed' if any(flags) else 'preparation_only')
                prompts=' '.join(result['option_comparisons'][0]['review_prompts'])
                if any(flags):
                    self.assertIn('no trial, meeting, delay or commitment is proposed',prompts)
                    self.assertNotIn('before considering a trial',prompts)
                if flags[0]:
                    self.assertIn('does not propose contacting anyone',prompts)
                    self.assertTrue(any('Pause ordinary negotiation' in item for item in result['constraint_notices']))
                if not any(flags):
                    self.assertTrue(any('does not establish' in item for item in result['constraint_notices']))
                self.assertIsNone(result['recommended_option'])

    def test_option_order_is_not_a_ranking(self):
        value=example();first=prepare_dispute(value)
        value['options'].reverse();second=prepare_dispute(value)
        self.assertEqual(first['option_comparisons'][0],second['option_comparisons'][1])
        self.assertEqual(first['option_comparisons'][1],second['option_comparisons'][0])
        self.assertIsNone(second['recommended_option'])

    def test_all_free_text_fields_screened_separately(self):
        locations=[('decision',),('my_position',),('partner_position_reported',),
                   ('facts','reported_agreed',0),('facts','disputed',0),('facts','unknowns',0),
                   ('options',0,'label'),('options',0,'description'),('options',0,'open_questions',0)]
        for location in locations:
            value=example();node=value
            for part in location[:-1]:node=node[part]
            node[location[-1]]='attack'
            with self.subTest(location=location),self.assertRaisesRegex(ValueError,'first-pass harm filter'):
                prepare_dispute(value)
        value=example();value['my_position']='prevent';value['partner_position_reported']='attack'
        with self.assertRaisesRegex(ValueError,'first-pass harm filter'):prepare_dispute(value)
        value['partner_position_reported']='prevent attack'
        self.assertIsNone(prepare_dispute(value)['recommended_option'])

    def test_strict_shapes_types_and_missing_choices_rejected(self):
        invalid=[]
        for field in example():
            value=example();del value[field];invalid.append(value)
        value=example();value['extra']='not allowed';invalid.append(value)
        for flag in (None,0,1,'false'):
            value=example();value['constraints']['safety_concern']=flag;invalid.append(value)
        for bad in (None,{},[],[example()['options'][0]],example()['options']*3):
            value=example();value['options']=bad;invalid.append(value)
        for field in ('my_fit','reported_partner_fit','reversibility','agreement'):
            value=example();value['options'][0][field]=True;invalid.append(value)
        value=example();value['options'][0]['action']='send';invalid.append(value)
        for value in invalid:
            with self.subTest(value_type=type(value)),self.assertRaises(ValueError):prepare_dispute(value)

    def test_duplicate_and_conflicting_labels_rejected(self):
        for second in ('Limited test','LIMITED TEST'):
            value=example();value['options'][1]['label']=second
            with self.assertRaises(ValueError):prepare_dispute(value)
        value=example();value['options'][0]['label']='Café';value['options'][1]['label']='Cafe\u0301'
        with self.assertRaises(ValueError):prepare_dispute(value)
        value=example();value['facts']['disputed']=list(value['facts']['reported_agreed'])
        with self.assertRaises(ValueError):prepare_dispute(value)

    def test_text_bounds_controls_unicode_and_no_error_echo(self):
        for invalid in ('',' trimmed ','x'*501,'private-marker\x1b[31m','private-marker\u202e','private-marker\ud800','private-marker\u2028','private-marker\u2029'):
            value=example();value['decision']=invalid
            with self.subTest(kind=repr(invalid[:20])),self.assertRaises(ValueError) as error:
                prepare_dispute(value)
            self.assertNotIn('private-marker',str(error.exception))
        value=example();value['decision']='આપણે કયા વિકલ્પ વિશે વધુ જાણવું જોઈએ?'
        self.assertEqual(prepare_dispute(value)['worksheet']['decision'],value['decision'])

    def test_json_bounds_duplicates_and_utf8(self):
        raw=json.dumps(example()).encode()
        self.assertEqual(parse_worksheet(raw),example())
        for bad in (b'',b'\xff',b'null',raw[:-1]+b',"decision":"duplicate"}',b'x'*(MAX_INPUT_BYTES+1)):
            with self.subTest(prefix=bad[:10]),self.assertRaises(ValueError):parse_worksheet(bad)
        self.assertLess(len(json.dumps(prepare_dispute(example())).encode()),MAX_OUTPUT_BYTES)

    def test_builder_has_no_network_or_engine_dependency(self):
        with (patch('jace.engine.CognitiveEngine',side_effect=AssertionError('engine not allowed')),
              patch('urllib.request.build_opener',side_effect=AssertionError('network not allowed'))):
            self.assertFalse(prepare_dispute(example())['provider_called'])


class DisputeAPITests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.reasoner=Mock();self.reasoner.respond.side_effect=AssertionError('provider not allowed')
        self.engine=CognitiveEngine(db_path=Path(self.directory.name)/'db',reasoner=self.reasoner)
        self.engine.remember('alice','I prefer private fixture memories not included in worksheets')
        self.server=JaceHTTPServer(('127.0.0.1',0),self.engine,ApiAuthorization({TOKEN:'alice'}))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01});self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3);self.engine.close();self.directory.cleanup()

    def call(self,body=None,*,token=TOKEN,raw=None,headers=None):
        fields={'Content-Type':'application/json','Authorization':'Bearer '+token};fields.update(headers or {})
        req=Request(f'http://127.0.0.1:{self.server.server_port}/v1/plans/dispute',
                    data=json.dumps(body).encode() if raw is None else raw,headers=fields,method='POST')
        try:response=urlopen(req,timeout=3)
        except HTTPError as error:response=error
        with response:return response.status,json.load(response),response.headers

    def test_authenticated_worksheet_does_not_read_or_write_engine_even_when_busy(self):
        changes=self.engine.memory.connection.total_changes
        with self.engine.request_admission(),patch('jace.api.JaceHandler.engine',new_callable=unittest.mock.PropertyMock,
                side_effect=AssertionError('engine access not allowed')):
            status,result,headers=self.call({'worksheet':example()},headers={'Origin':'http://127.0.0.1:8080'})
        self.assertEqual(status,200);self.assertFalse(result['saved'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(headers['Access-Control-Allow-Origin'],'http://127.0.0.1:8080')
        self.assertNotIn('private fixture memories',json.dumps(result))
        self.assertEqual(self.engine.memory.connection.total_changes,changes)
        self.reasoner.respond.assert_not_called()

    def test_auth_ownership_origin_and_exact_body_fields(self):
        self.assertEqual(self.call({'worksheet':example()},token='')[0],401)
        self.assertEqual(self.call({'user_id':'bob','worksheet':example()})[0],403)
        self.assertEqual(self.call({'worksheet':example()},headers={'Origin':'https://other.invalid'})[0],403)
        self.assertEqual(self.call({'worksheet':example(),'learn':True})[0],400)
        self.assertEqual(self.call({'worksheet':example(),'reasoner_mode':'configured'})[0],400)
        self.assertEqual(self.call({})[0],400)
        self.reasoner.respond.assert_not_called()

    def test_duplicate_json_and_bad_nested_input_do_not_echo_or_persist(self):
        changes=self.engine.memory.connection.total_changes
        self.assertEqual(self.call(raw=b'{"worksheet":{},"worksheet":{}}')[0],400)
        value=example();value['options'][0]['label']='private-marker\x1b'
        status,body,_=self.call({'worksheet':value})
        self.assertEqual(status,400);self.assertNotIn('private-marker',json.dumps(body))
        self.assertEqual(self.engine.memory.connection.total_changes,changes)


class DisputeCLITests(unittest.TestCase):
    def run_cli(self,raw,args=('--stdin',)):
        with tempfile.TemporaryDirectory() as directory:
            db=Path(directory)/'never-created.db'
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),JACE_DB_PATH=str(db),
                     JACE_CANONICAL_PATH=str(Path(directory)/'missing-source.json'),
                     JACE_LLM_URL='invalid-model-endpoint-must-not-be-read',JACE_LLM_API_KEY='synthetic-not-real')
            result=subprocess.run([sys.executable,'-m','jace.cli','prepare-dispute',*args],input=raw,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=directory,env=env,timeout=5)
            self.assertFalse(db.exists())
            self.assertEqual(list(Path(directory).iterdir()),[])
            return result

    def test_cli_uses_stdin_and_ignores_provider_source_database_configuration(self):
        result=self.run_cli(json.dumps(example()).encode())
        self.assertEqual(result.returncode,0,result.stderr)
        body=json.loads(result.stdout);self.assertFalse(body['saved']);self.assertFalse(body['provider_called'])
        self.assertEqual(body['worksheet'],example());self.assertEqual(result.stderr,b'')

    def test_cli_requires_explicit_stdin_and_suppresses_private_error_details(self):
        result=self.run_cli(b'',args=())
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
        value=example();value['decision']='private-marker\x1b'
        result=self.run_cli(json.dumps(value).encode())
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
        self.assertNotIn(b'private-marker',result.stderr)

    def test_cli_bounds_final_pretty_printed_utf8_bytes_before_stdout(self):
        value=example();option=deepcopy(value['options'][0]);value['options']=[]
        for index in range(4):
            row=deepcopy(option);row['label']=str(index);row['description']='é'*600
            row['open_questions']=[str(question)+'é'*399 for question in range(5)]
            value['options'].append(row)
        value['facts']['reported_agreed']=['é'*12+str(index) for index in range(8)]
        raw=json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.assertLessEqual(len(raw),MAX_INPUT_BYTES)
        report=prepare_dispute(value)
        self.assertLessEqual(len(json.dumps(report,ensure_ascii=False).encode('utf-8')),MAX_OUTPUT_BYTES)
        self.assertGreater(len((json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode('utf-8')),MAX_OUTPUT_BYTES)
        result=self.run_cli(raw)
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
        self.assertIn(b'CLI output exceeds the 64 KiB limit',result.stderr)

    def test_cli_oversized_input_rejected_before_any_engine(self):
        result=self.run_cli(b'x'*(MAX_INPUT_BYTES+1))
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')


if __name__=='__main__':unittest.main()
