import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jace import cli
from jace.wardrobe import CATEGORIES, build_wardrobe_plan


def inventory():
    return {'items':[dict(label='My shirts',category='tops',quantity=4,condition='ready',fit='fits',
                         use='unused',preserve=False,ownership='mine')],
            'minimum_ready':{c:2 if c=='tops' else 0 for c in CATEGORIES}}


class Input:
    def __init__(self,raw): self.buffer=io.BytesIO(raw)


class StatelessWardrobeTests(unittest.TestCase):
    def invoke(self,raw,args=('--stdin','--allow-local-disclosure'),output=None):
        source=Input(raw); out=output if output is not None else io.StringIO(); err=io.StringIO()
        with patch('sys.argv',['jace','preview-wardrobe',*args]),patch('sys.stdin',source), \
             contextlib.redirect_stdout(out),contextlib.redirect_stderr(err), \
             patch('jace.cli.CognitiveEngine',side_effect=AssertionError('no engine')), \
             patch('sqlite3.connect',side_effect=AssertionError('no database')), \
             patch('jace.canonical.CanonicalStore',side_effect=AssertionError('no corpus')):
            try: cli.main();code=0
            except SystemExit as error: code=error.code
        return code,out.getvalue(),err.getvalue(),source.buffer.tell()

    def test_both_flags_required_before_input_read(self):
        for args in ((),('--stdin',),('--allow-local-disclosure',)):
            code,out,err,read=self.invoke(json.dumps(inventory()).encode(),args)
            self.assertEqual(code,2);self.assertEqual(out,'');self.assertEqual(read,0)

    def test_pure_planner_result_preserved_without_persistence(self):
        value=inventory(); raw=json.dumps(value).encode()
        code,out,err,_=self.invoke(raw)
        self.assertEqual(code,0,err)
        expected=build_wardrobe_plan(value);expected.update(mode='stateless_preview',inventory_saved=False)
        self.assertEqual(json.loads(out),expected)
        self.assertEqual(value,inventory())
        self.assertFalse(expected['actions_executed']);self.assertIsNone(expected['action'])

    def test_ownership_and_preservation_are_not_relaxed(self):
        for owner,preserve,decision in [('shared',False,'ownership_review'),('mine',True,'preserve')]:
            value=inventory();value['items'][0].update(ownership=owner,preserve=preserve)
            code,out,err,_=self.invoke(json.dumps(value).encode())
            self.assertEqual(code,0,err)
            self.assertEqual(json.loads(out)['item_steps'][0]['decision'],decision)

    def test_duplicate_unknown_invalid_and_unicode_inputs(self):
        for raw in (b'{"items":[],"items":[]}',b'[]',b'\xff',b'{"private-secret":1}',b'['*5000):
            code,out,err,_=self.invoke(raw)
            self.assertEqual(code,2);self.assertEqual(out,'');self.assertNotIn('private-secret',err)
        value=inventory();value['items'][0]['label']='કપડાં'
        code,out,err,_=self.invoke(json.dumps(value,ensure_ascii=False).encode())
        self.assertEqual(code,0,err);self.assertIn('કપડાં',out)

    def test_all_existing_inventory_bounds_apply(self):
        for mutate in (lambda v:v['items'][0].update(quantity=True),
                       lambda v:v['items'][0].update(quantity=101),
                       lambda v:v.update(items=v['items']*31),
                       lambda v:v['minimum_ready'].update(tops=51),
                       lambda v:v['items'][0].update(label='x'*61)):
            value=inventory();mutate(value)
            code,out,err,_=self.invoke(json.dumps(value).encode())
            self.assertEqual(code,2);self.assertEqual(out,'')

    def test_input_byte_bound_and_output_bound(self):
        raw=json.dumps(inventory()).encode();bounded=raw+b' '*(65536-len(raw))
        code,_,err,read=self.invoke(bounded);self.assertEqual(code,0,err);self.assertEqual(read,65536)
        code,out,_,read=self.invoke(bounded+b' '*10000)
        self.assertEqual(code,2);self.assertEqual(out,'');self.assertEqual(read,65537)
        with patch('jace.cli.json.dumps',return_value='x'*131073):
            code,out,err,_=self.invoke(raw)
        self.assertEqual(code,2);self.assertEqual(out,'')

    def test_output_error_is_generic_and_partial_output_is_possible(self):
        class FailingOutput(io.StringIO):
            def write(self,text):
                super().write(text[:8]);raise OSError('private-secret destination')
        code,out,err,_=self.invoke(json.dumps(inventory()).encode(),output=FailingOutput())
        self.assertEqual(code,2);self.assertTrue(out)
        self.assertIn('output may be incomplete',err);self.assertNotIn('private-secret',err)

    def test_real_pipe_ignores_configured_database_source_and_model(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            env=dict(os.environ,PYTHONPATH=str(root/'src'),PYTHONDONTWRITEBYTECODE='1',
                     JACE_DB_PATH=directory+'/never.sqlite',JACE_CANONICAL_PATH='/private/never.json',
                     JACE_LLM_URL='intentionally-invalid-never-load')
            run=subprocess.run([sys.executable,'-m','jace.cli','preview-wardrobe','--stdin','--allow-local-disclosure'],
                input=json.dumps(inventory()).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=root,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(list(Path(directory).iterdir()),[])
            self.assertFalse(json.loads(run.stdout)['inventory_saved'])
            self.assertNotIn(b'/private',run.stdout+run.stderr)

if __name__ == '__main__':unittest.main()
