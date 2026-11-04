import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jace.bundle_builder import build_exact_bundle
from jace.canonical import CanonicalStore
from jace.engine import CognitiveEngine
from jace.model_output import check_model_output,source_integrity_reference,checked_text
from jace.models import CanonicalEntry
from jace.reasoner import LocalReasoner
from jace.source_bundle import MAX_MANIFEST_BYTES, load_builtin_samples, write_source_bundle

RAW='  Synthetic α  lantern\r\nuses\ta reversible path.\nAnother reviewed fixture.  '.encode()
def metadata(digest,start,end,ident='fixture:source'):
    return dict(entry_id=ident,title='Original fixture',guidance='Interpretation is separate.',source='Original synthetic fixture',
        work='Original fixture work',language='en',edition=None,location='Fixture byte excerpt',license='CC0-1.0',verified=True,
        tags=[],source_ref={'sha256':digest,'start':start,'end':end})

class SourceRuntimeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def bundle(self,name='bundle',data=RAW,ident='fixture:source'):
        digest=hashlib.sha256(data).hexdigest();return write_source_bundle(self.root/name,{digest:data},[metadata(digest,0,len(data),ident)])
    def test_runtime_preserves_exact_bytes_and_exposes_only_digest_span(self):
        path=self.bundle();store=CanonicalStore(path);entry=store.all()[0]
        self.assertTrue(store.source_bound);self.assertEqual(entry.principle.encode(),RAW)
        data=entry.to_dict();self.assertEqual(data['source_sha256'],hashlib.sha256(RAW).hexdigest())
        self.assertEqual((data['source_byte_start'],data['source_byte_end']),(0,len(RAW)))
        self.assertNotIn(str(self.root),json.dumps(data));self.assertIsInstance(entry.tags,tuple)
        data['tags'].append('untrusted');self.assertNotIn('untrusted',store.all()[0].tags)
        self.assertEqual(store.search('lantern')[0],entry)
    def test_quote_offsets_count_utf8_bytes_and_preserve_crlf(self):
        entry=CanonicalStore(self.bundle()).all()[0];quote='lantern\r\nuses\ta reversible'
        result=check_model_output(json.dumps({'answer':'A synthetic explanation.','citations':[{'entry_id':entry.entry_id,'quote':quote}]}),[entry]);rendered=result.render()
        start=RAW.index(quote.encode());end=start+len(quote.encode())
        self.assertIn(quote,rendered);self.assertIn(f'[{start}, {end})',rendered);self.assertIn('not authorship',rendered)
        checked_text(rendered,'rendered',32768,allow_crlf=True)
        with self.assertRaises(ValueError):checked_text('line\roverwrite','unsafe',100,allow_crlf=True)
        with self.assertRaises(ValueError):check_model_output(json.dumps({'answer':'line\r\nanswer','citations':[]}),[entry])
        self.assertIn('Source bytes checked at admission',LocalReasoner._grounding([entry]))
    def test_quote_repetition_is_explicit_first_occurrence(self):
        raw='α marker and marker'.encode();entry=CanonicalStore(self.bundle(data=raw)).all()[0]
        self.assertIn('[3, 9)',source_integrity_reference(entry,'marker'));self.assertIn('first matching occurrence',source_integrity_reference(entry,'marker'))
    def test_tampered_source_rejected_but_loaded_snapshot_stays_immutable(self):
        path=self.bundle();first=CanonicalStore(path);digest=hashlib.sha256(RAW).hexdigest()
        (path.parent/'sources'/f'{digest}.txt').write_bytes(b'Altered bytes')
        with self.assertRaises(ValueError):CanonicalStore(path)
        self.assertEqual(first.all()[0].principle.encode(),RAW)
    def test_two_live_engine_corpora_remain_isolated_and_preserve_memories(self):
        first_path=self.bundle('a',b'Original lantern words.');second_path=self.bundle('b',b'Other compass words.')
        first=CognitiveEngine(self.root/'db',canonical_path=first_path,reasoner=LocalReasoner())
        saved=first.remember('alice','I prefer lantern fixtures')[0]
        second=CognitiveEngine(self.root/'db',canonical_path=second_path,reasoner=LocalReasoner())
        try:
            self.assertTrue(first.search_graph('lantern','bob'));self.assertFalse(second.search_graph('lantern','bob'))
            self.assertTrue(second.search_graph('compass','bob'));self.assertFalse(first.search_graph('compass','bob'))
            self.assertEqual(second.memory.get_owned('alice',saved.memory_id),saved)
            answer=first.think('alice','Explain the lantern fixture');self.assertEqual(answer.canonical_evidence[0].source_sha256,hashlib.sha256(b'Original lantern words.').hexdigest())
        finally:first.close();second.close()
    def test_bad_admission_does_not_change_existing_graph_or_memory(self):
        original=CognitiveEngine(self.root/'db',reasoner=LocalReasoner());saved=original.remember('alice','I prefer quiet')[0];before=original.graph.stats()
        path=self.bundle();d=json.loads(path.read_text());d['records'][0]['source_ref']['end']+=1;path.write_text(json.dumps(d))
        try:
            with self.assertRaises(ValueError):CognitiveEngine(self.root/'db',canonical_path=path,reasoner=LocalReasoner())
            self.assertEqual(original.graph.stats(),before);self.assertEqual(original.memory.get_owned('alice',saved.memory_id),saved)
        finally:original.close()
    def test_legacy_rejects_integrity_claims_unknown_keys_and_bad_types(self):
        entry=CanonicalStore(self.bundle()).all()[0].to_dict()
        path=self.root/'legacy.json';path.write_text(json.dumps([entry]))
        with self.assertRaises(ValueError):CanonicalStore(path)
        for field in ('source_sha256','source_byte_start','source_byte_end'):entry.pop(field)
        for delta in ({'source_sha256':None},{'verified':1},{'title':[]},{'tags':['x']*33},{'tags':'lantern'},{'principle':'x'*20001},{'extra':'ignored'}):
            path.write_text(json.dumps([{**entry,**delta}]))
            with self.subTest(delta=delta),self.assertRaises(ValueError):CanonicalStore(path)
        path.write_text(json.dumps([entry]));legacy=CanonicalStore(path).all()[0];self.assertIn('record-only',source_integrity_reference(legacy))
    def test_legacy_serialization_and_namespace_unchanged(self):
        e=CanonicalEntry('fixture','Title','Text','Guidance','Source',['fixture'])
        expected=dict(entry_id='fixture',title='Title',principle='Text',guidance='Guidance',source='Source',tags=['fixture'],work=None,language='en',edition=None,location=None,license=None,verified=False)
        self.assertEqual(e.to_dict(),expected)
        self.assertNotIn('source_sha256',CanonicalStore().all()[0].to_dict())
    def test_default_package_samples_work_without_safe_external_io(self):
        with patch('jace.source_bundle._require_safe_io',side_effect=ValueError('POSIX unavailable')):
            store=CanonicalStore();self.assertFalse(store.source_bound);self.assertEqual(len(store.all()),6)
            self.assertEqual(CanonicalStore('').all(),store.all())
            engine=CognitiveEngine(self.root/'portable.db',reasoner=LocalReasoner())
            try:self.assertTrue(engine.think('alice','Explain ahimsa').response)
            finally:engine.close()
            # Even an explicit path to the package file uses external admission.
            with self.assertRaises(ValueError):CanonicalStore(store.path)
            with patch.dict('os.environ',{'JACE_CANONICAL_PATH':'/unread/external/bundle.json'}):
                engine=CognitiveEngine(self.root/'override.db',canonical_path='',reasoner=LocalReasoner())
                try:self.assertEqual(engine.canonical.all(),store.all())
                finally:engine.close()
            with patch.dict('os.environ',{'JACE_CANONICAL_PATH':''}):
                engine=CognitiveEngine(self.root/'empty-env.db',reasoner=LocalReasoner())
                try:self.assertEqual(engine.canonical.all(),store.all())
                finally:engine.close()
            for invalid in (False,0):
                with self.assertRaises((TypeError,ValueError)):CanonicalStore(invalid)
    def test_builtin_package_reader_still_bounds_and_checks_json(self):
        for raw in (b'x'*(MAX_MANIFEST_BYTES+1),b'{}',b'[{"x":1,"x":2}]',b'["\xff"]'):
            with patch('jace.source_bundle.importlib.resources.files') as files:
                files.return_value.joinpath.return_value.open.return_value=io.BytesIO(raw)
                with self.assertRaises(ValueError):load_builtin_samples()
        with patch('jace.canonical.load_builtin_samples',return_value=[{'source_sha256':None}]):
            with self.assertRaises(ValueError):CanonicalStore()
    def test_false_partial_source_reference_cannot_be_cited(self):
        entry=CanonicalStore(self.bundle()).all()[0]
        from dataclasses import replace
        for changed in (replace(entry,source_byte_end=True),replace(entry,source_sha256=None),replace(entry,source_byte_end=len(RAW)-1)):
            with self.assertRaises(ValueError):check_model_output(json.dumps({'answer':'Text','citations':[{'entry_id':changed.entry_id,'quote':'Synthetic'}]}),[changed])

class ExactBundleBuilderTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'fixture.txt';self.source.write_bytes(RAW)
    def tearDown(self):self.temp.cleanup()
    def build(self,**changes):
        opts=dict(work='Fixture work',source='Original synthetic fixture',language='en',license_name='CC0-1.0',location='Fixture file',verified=True,confirm_build=True,chunk_words=3,overlap_words=1);opts.update(changes)
        return build_exact_bundle([self.source],self.root/'out',**opts)
    def test_exact_spans_keep_original_whitespace_and_overlap(self):
        path=self.build();entries=CanonicalStore(path).all();self.assertGreater(len(entries),1)
        self.assertEqual(entries[0].principle,'Synthetic α  lantern')
        self.assertEqual(entries[1].principle,'lantern\r\nuses\ta')
        for e in entries:self.assertEqual(RAW[e.source_byte_start:e.source_byte_end].decode(),e.principle)
    def test_confirmation_and_review_required_before_read_and_no_overwrite(self):
        for changes in ({'confirm_build':False},{'verified':False},{'license_name':''},{'chunk_words':True},{'overlap_words':3}):
            with patch('jace.bundle_builder.read_source_file',side_effect=AssertionError('must not read')),self.assertRaises(ValueError):self.build(**changes)
        self.assertFalse((self.root/'out').exists());path=self.build();before=path.read_bytes()
        with self.assertRaises((ValueError,FileExistsError)):self.build()
        self.assertEqual(path.read_bytes(),before)
    def test_record_budget_empty_and_long_word_never_publish_partial(self):
        self.source.write_text(' '.join('word'+str(i) for i in range(257)))
        with self.assertRaises(ValueError):self.build(chunk_words=1,overlap_words=0)
        self.assertFalse((self.root/'out').exists())
        for text in ('   \n\t','x'*20001):
            self.source.write_text(text)
            with self.assertRaises(ValueError):self.build()
            self.assertFalse((self.root/'out').exists())
    def test_cli_preview_does_not_read_input_and_confirmed_build_is_local(self):
        root=Path(__file__).resolve().parents[1];base=[sys.executable,str(root/'scripts/build_source_bundle.py'),str(self.source),'--output',str(self.root/'out'),'--work','Fixture','--source','Original fixture','--language','en','--license','CC0-1.0','--location','fixture']
        self.source.unlink();preview=subprocess.run(base,capture_output=True,text=True,timeout=5);self.assertEqual(preview.returncode,0,preview.stderr);self.assertIn('No files were copied or read',preview.stdout)
        self.source.write_bytes(RAW);built=subprocess.run(base+['--verified','--confirm-build'],capture_output=True,text=True,timeout=5);self.assertEqual(built.returncode,0,built.stderr);self.assertTrue(CanonicalStore(self.root/'out'/'bundle.json').source_bound)

if __name__=='__main__':unittest.main()
