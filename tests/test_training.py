"""Admission/orchestration tests only. No ML dependencies or real training."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.training import admit_dataset, admit_model, prepare_training, run_training
from jace import training_worker

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfflineTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json'):
            (self.root / name).write_bytes((ROOT / 'training/fixtures' / name).read_bytes())
        self.model = self.root / 'model'; self.model.mkdir()
        config = {'model_type':'llama', 'architectures':['LlamaForCausalLM'], 'hidden_size':8,
                  'intermediate_size':16, 'num_hidden_layers':1, 'num_attention_heads':1,
                  'num_key_value_heads':1, 'max_position_embeddings':128, 'vocab_size':8,
                  'eos_token_id':2, 'bos_token_id':1, 'pad_token_id':0}
        (self.model / 'config.json').write_text(json.dumps(config))
        (self.model / 'tokenizer.json').write_text(json.dumps({'model': {'type':'WordLevel', 'vocab':{'[UNK]':0}, 'unk_token':'[UNK]'}}))
        # Inert bytes for preflight tests, deliberately NOT an executable compatible model.
        self.write_weights({'fixture.weight':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}, b'\0'*4)
        self.refresh_model_manifest()
        self.args = (self.root/'train.jsonl', self.root/'evaluation.jsonl', self.root/'manifest.json', self.model, self.root/'model-manifest.json')

    def tearDown(self):
        self.temp.cleanup()

    def write_weights(self, header, data=b'\0'*4):
        raw = json.dumps(header).encode()
        (self.model/'model.safetensors').write_bytes(struct.pack('<Q',len(raw))+raw+data)

    def refresh_model_manifest(self):
        manifest = {'source':'synthetic inert header fixture, not a pretrained model','license':'MIT','rights_reviewed':True,
                    'files':{p.name:digest(p) for p in self.model.iterdir() if p.is_file()}}
        (self.root/'model-manifest.json').write_text(json.dumps(manifest))

    def edit_dataset_manifest(self, **updates):
        path=self.root/'manifest.json'; data=json.loads(path.read_text()); data.update(updates); path.write_text(json.dumps(data))

    def refresh_dataset_hashes(self):
        self.edit_dataset_manifest(train_sha256=digest(self.root/'train.jsonl'), evaluation_sha256=digest(self.root/'evaluation.jsonl'))

    def job(self, output='run'):
        plan=prepare_training(*self.args)
        return {'train':str(self.args[0]),'evaluation':str(self.args[1]),'dataset_manifest':str(self.args[2]),
                'model':str(self.args[3]),'model_manifest':str(self.args[4]),'output':str(self.root/output),
                'steps':5,'sequence_length':128,'expected_dataset':plan['data']['manifest_sha256'],
                'expected_model':plan['model']['manifest_sha256'],'confirm_training':True}

    def test_fixture_preflight_has_distinct_heldout_and_no_execution(self):
        with patch('jace.training.subprocess.run', side_effect=AssertionError('no execution')):
            plan=prepare_training(*self.args)
        self.assertEqual(len(plan['data']['train']),3)
        self.assertEqual(len(plan['data']['evaluation']),2)
        self.assertFalse((self.root/'run').exists())
        self.assertEqual(plan['model']['tensor_parameters'],1)

    def test_rights_privacy_and_synthetic_only_admission(self):
        baseline=(self.root/'manifest.json').read_bytes()
        for updates in [{'data_kind':'private_memory'}, {'data_kind':'reviewed_corpus'}, {'rights_reviewed':False},
                        {'rights_reviewed':1}, {'content_reviewed':False}, {'contains_personal_data':True},
                        {'contains_personal_data':0}, {'license':''}, {'schema_version':True}]:
            (self.root/'manifest.json').write_bytes(baseline)
            self.edit_dataset_manifest(**updates)
            with self.subTest(updates=updates),self.assertRaises(ValueError):
                admit_dataset(*self.args[:3])

    def test_hash_drift_invalid_json_unknown_fields_and_empty_split(self):
        original=(self.root/'evaluation.jsonl').read_bytes()
        for raw in [b'', b'[]\n', b'{"id":"same","id":"duplicate"}\n', b'not json\n', b'\n',
                    b'{"id":"x","instruction":"x","response":"x","private":true}\n']:
            (self.root/'evaluation.jsonl').write_bytes(raw)
            with self.assertRaises(ValueError): admit_dataset(*self.args[:3])
            self.refresh_dataset_hashes()
            with self.assertRaises(ValueError): admit_dataset(*self.args[:3])
        (self.root/'evaluation.jsonl').write_bytes(original)

    def test_duplicate_ids_and_normalized_prompts_cannot_leak_to_holdout(self):
        row=json.loads((self.root/'train.jsonl').read_text().splitlines()[0])
        for changes in [{'id':row['id'],'instruction':'Different prompt'},
                        {'id':'different','instruction':row['instruction'].upper().replace(' ', '  ')}]:
            (self.root/'evaluation.jsonl').write_text(json.dumps(dict(row,**changes))+'\n')
            self.refresh_dataset_hashes()
            with self.assertRaises(ValueError): admit_dataset(*self.args[:3])

    def test_byte_record_text_and_training_budgets(self):
        (self.root/'evaluation.jsonl').write_bytes(b'x'*(2*1024*1024+1))
        with self.assertRaises(ValueError): admit_dataset(*self.args[:3])
        for name in ('train.jsonl','evaluation.jsonl','manifest.json'):
            (self.root/name).write_bytes((ROOT/'training/fixtures'/name).read_bytes())
        for steps,length in [(0,128),(21,128),(True,128),(5,257),(5,31),(5,True),(5,129)]:
            with self.subTest(steps=steps,length=length),self.assertRaises(ValueError):
                prepare_training(*self.args,steps=steps,sequence_length=length)
        # Restore data to exercise record and string budgets separately.
        for name in ('train.jsonl','evaluation.jsonl','manifest.json'):
            (self.root/name).write_bytes((ROOT/'training/fixtures'/name).read_bytes())
        rows=[{'id':f'eval-{i}','instruction':f'Synthetic distinct {i}','response':'x'} for i in range(257)]
        for records in [rows,[{'id':'long','instruction':'x'*4097,'response':'x'}]]:
            (self.root/'evaluation.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records)); self.refresh_dataset_hashes()
            with self.assertRaises(ValueError): admit_dataset(*self.args[:3])

    def test_files_paths_and_remote_code_are_rejected_before_loading(self):
        for filename in ['model.bin','policy.pt','custom.py','model.safetensors.index.json']:
            extra=self.model/filename; extra.write_bytes(b'not loaded')
            with self.assertRaises(ValueError): admit_model(*self.args[3:])
            extra.unlink()
        config_path=self.model/'config.json'; original=config_path.read_text()
        for update in [{'auto_map':{'AutoModel':'custom.Model'}},{'model_type':'custom'},{'hidden_size':True},
                       {'hidden_size':512,'intermediate_size':2048,'num_hidden_layers':8,'vocab_size':8192},
                       {'architectures':['CustomModel']},{'rope_theta':float('inf')},{'rope_theta':10**1000}]:
            config=json.loads(original);config.update(update);config_path.write_text(json.dumps(config));self.refresh_model_manifest()
            with self.assertRaises(ValueError): admit_model(*self.args[3:])
        config_path.write_text(original);self.refresh_model_manifest()
        linked=self.root/'linked-model';linked.symlink_to(self.model,target_is_directory=True)
        with self.assertRaises(ValueError): admit_model(linked,self.args[4])
        parentlink=self.root/'linked-parent';parentlink.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError): admit_dataset(parentlink/'train.jsonl',*self.args[1:3])
        config_path.unlink();config_path.symlink_to(self.root/'manifest.json')
        with self.assertRaises(ValueError): admit_model(*self.args[3:])

    def test_tensor_header_shape_offset_type_and_budget_validation(self):
        bad=[({'x':{'dtype':[],'shape':[1],'data_offsets':[0,4]}},b'\0'*4),
             ({'x':{'dtype':'F32','shape':[True],'data_offsets':[0,4]}},b'\0'*4),
             ({'x':{'dtype':'I64','shape':[1],'data_offsets':[0,4]}},b'\0'*4),
             ({'x':{'dtype':'F32','shape':[8192,8192],'data_offsets':[0,4]}},b'\0'*4),
             ({'x':{'dtype':'F32','shape':[1],'data_offsets':[1,5]}},b'\0'*5),
             ({'x':{'dtype':'F32','shape':[1],'data_offsets':[0,4]},'y':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}},b'\0'*4),
             ({'x':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}},b'\0'*8)]
        for header,body in bad:
            self.write_weights(header,body);self.refresh_model_manifest()
            with self.assertRaises(ValueError):admit_model(*self.args[3:])
        (self.model/'model.safetensors').write_bytes(b'\xff'*8);self.refresh_model_manifest()
        with self.assertRaises(ValueError):admit_model(*self.args[3:])

    def test_confirmation_output_collision_and_worker_env(self):
        for value in [False,1,'true',None]:
            with patch('jace.training.subprocess.run') as run,self.assertRaises(ValueError):
                run_training(*self.args,self.root/'run',confirm_training=value)
            run.assert_not_called()
        (self.root/'existing').mkdir();(self.root/'existing'/'keep').write_text('keep')
        with self.assertRaises(ValueError):run_training(*self.args,self.root/'existing',confirm_training=True)
        self.assertEqual((self.root/'existing'/'keep').read_text(),'keep')
        # Mock process plumbing only, not actual training.
        fake=subprocess.CompletedProcess([],0,'{"completed":true,"mock_only":true}','')
        with patch.dict(os.environ,{'HF_TOKEN':'synthetic-secret-not-real','AWS_ACCESS_KEY_ID':'synthetic-not-real'}),patch('jace.training.subprocess.run',return_value=fake) as run:
            result=run_training(*self.args,self.root/'run',confirm_training=True)
        self.assertTrue(result['mock_only'])
        kw=run.call_args.kwargs
        self.assertEqual(kw['timeout'],180)
        self.assertEqual(Path(kw['cwd']),ROOT/'src')
        self.assertEqual(kw['env']['PYTHONNOUSERSITE'],'1')
        self.assertNotIn('HF_TOKEN',kw['env']);self.assertNotIn('AWS_ACCESS_KEY_ID',kw['env'])
        self.assertEqual(kw['env']['HF_HUB_OFFLINE'],'1');self.assertEqual(kw['env']['HF_HUB_DISABLE_TELEMETRY'],'1')
        self.assertTrue(json.loads(kw['input'])['confirm_training'])

    def test_process_failure_timeout_or_incomplete_report_is_not_success(self):
        for failure in [subprocess.CompletedProcess([],2,'','synthetic worker failure'),
                        subprocess.CompletedProcess([],0,'{"completed":false}',''),
                        subprocess.TimeoutExpired([],180)]:
            with patch('jace.training.subprocess.run', side_effect=failure if isinstance(failure,Exception) else None,
                       return_value=failure),self.assertRaises(RuntimeError):
                run_training(*self.args,self.root/'run',confirm_training=True)

    def test_worker_changed_input_and_backend_failure_have_no_success_marker(self):
        job=self.job();job['expected_dataset']='changed'
        with patch.object(training_worker,'_limits',return_value={}),patch.object(training_worker,'_train_qlora') as backend,self.assertRaises(ValueError):
            training_worker.execute(job)
        backend.assert_not_called();self.assertFalse((self.root/'run').exists())
        job=self.job()
        with patch.object(training_worker,'_limits',return_value={}),patch.object(training_worker,'_train_qlora',side_effect=RuntimeError('mock backend failure')),patch.dict(os.environ,{},clear=False):
            with self.assertRaises(RuntimeError):training_worker.execute(job)
        self.assertFalse((self.root/'run'/'manifest.json').exists())
        self.assertFalse((self.root/'run'/'.inputs').exists())
        self.assertEqual(json.loads((self.root/'run'/'FAILED.json').read_text())['completed'],False)

    def test_mocked_export_publication_uses_private_snapshot_and_adapter_only_manifest(self):
        def backend(plan,model,stage):
            self.assertNotEqual(model,self.model)
            self.assertEqual(model.parent.parent,self.root/'run')
            (stage/'adapter_model.safetensors').write_bytes(b'synthetic mock artifact, not real weights')
            (stage/'adapter_config.json').write_text('{}')
            return {'mock_only':True}
        with patch.object(training_worker,'_limits',return_value={'mock_only':True}),patch.object(training_worker,'_train_qlora',side_effect=backend),patch.object(training_worker,'_verify_export',return_value={'mock_only':True}),patch.dict(os.environ,{},clear=False):
            report=training_worker.execute(self.job())
        self.assertTrue(report['metrics']['mock_only'])
        output=self.root/'run'
        self.assertEqual(output.stat().st_mode & 0o777,0o700)
        self.assertFalse((output/'.inputs').exists());self.assertFalse((output/'.working').exists())
        self.assertEqual(set(p.name for p in output.iterdir()),{'adapter','manifest.json'})
        self.assertNotIn(str(self.root),json.dumps(report))

    def test_mock_export_rejects_unexpected_or_base_weights(self):
        stage=self.root/'stage';stage.mkdir()
        (stage/'model.bin').write_bytes(b'not loaded')
        with self.assertRaises(ValueError):training_worker._verify_export(stage)
        (stage/'model.bin').unlink()
        header=json.dumps({'base.weight':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode()
        (stage/'adapter_model.safetensors').write_bytes(struct.pack('<Q',len(header))+header+b'\0'*4)
        (stage/'adapter_config.json').write_text('{}')
        with self.assertRaises(ValueError):training_worker._verify_export(stage)

    def test_worker_resource_limits_in_separate_process_without_ml(self):
        code = "import json,resource; from jace.training_worker import _limits; r=_limits(); r['open_files']=resource.getrlimit(resource.RLIMIT_NOFILE)[0]; print(json.dumps(r))"
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        limits = json.loads(result.stdout)
        self.assertEqual(limits['address_space_bytes'], 4 * 1024**3)
        self.assertEqual(limits['cpu_seconds'], 120)
        self.assertEqual(limits['file_bytes'], 64 * 1024**2)
        self.assertEqual(limits['open_files'], 128)

    def test_source_change_during_mock_backend_prevents_completed_export(self):
        def backend(plan, model, stage):
            (self.root/'evaluation.jsonl').write_text('changed original input')
            return {'mock_only': True}
        with patch.object(training_worker, '_limits', return_value={}), patch.object(training_worker, '_train_qlora', side_effect=backend), patch.dict(os.environ, {}, clear=False):
            with self.assertRaises(ValueError):
                training_worker.execute(self.job())
        self.assertFalse((self.root/'run'/'manifest.json').exists())
        self.assertTrue((self.root/'run'/'FAILED.json').exists())
        self.assertFalse((self.root/'run'/'.inputs').exists())

    def test_actual_capped_worker_fails_without_optional_dependencies(self):
        # Real subprocess/limits and failure path, never a model-training test.
        import importlib.util
        if importlib.util.find_spec('torch') is not None:
            self.skipTest('negative environment probe requires Torch to be absent')
        with self.assertRaisesRegex(RuntimeError, 'Optional training dependencies are unavailable'):
            run_training(*self.args,self.root/'negative-run',confirm_training=True)
        self.assertFalse((self.root/'negative-run'/'manifest.json').exists())
        self.assertFalse((self.root/'negative-run'/'.inputs').exists())
        self.assertTrue((self.root/'negative-run'/'FAILED.json').is_file())

    def test_cli_default_is_preflight_not_training(self):
        command=[sys.executable,str(ROOT/'scripts/train_qlora.py'),str(self.args[0]),'--evaluation',str(self.args[1]),
                 '--dataset-manifest',str(self.args[2]),'--model',str(self.args[3]),'--model-manifest',str(self.args[4]),'--output',str(self.root/'run')]
        result=subprocess.run(command,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        body=json.loads(result.stdout);self.assertFalse(body['training_started']);self.assertTrue(body['preflight_passed'])
        self.assertFalse((self.root/'run').exists())


if __name__=='__main__':unittest.main()
