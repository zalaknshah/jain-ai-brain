"""Actual CPU optimization and reload tests, with no mocked training backend."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jace.evidence_router import (calibrate, digest, encoded, evaluate, fit, load_dataset,
                                 load_model, objective_gradient, vector)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'training/evidence_router'


class EvidenceRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dataset(FIXTURES)
        cls.model, cls.proof = fit(cls.data['train'], cls.data['corpus'])
        cls.model.update(manifest_sha256=cls.data['manifest_sha256'],
                         corpus_sha256=cls.data['manifest']['files']['corpus.json'],
                         thresholds={m:calibrate(cls.model, cls.data['corpus'], cls.data['development'], m)
                                     for m in ('lexical','tfidf','trained')})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for file in FIXTURES.iterdir():
            if file.is_file(): (self.root/file.name).write_bytes(file.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, name, value):
        (self.root/name).write_bytes(encoded(value))
        manifest=json.loads((self.root/'manifest.json').read_text())
        if name in manifest['files']:
            manifest['files'][name]=digest((self.root/name).read_bytes())
            (self.root/'manifest.json').write_bytes(encoded(manifest))

    def test_real_gradients_changed_weights_and_lower_loss(self):
        self.assertEqual(self.proof['steps'],400)
        self.assertNotEqual(self.proof['initial_weights_sha256'],self.proof['final_weights_sha256'])
        self.assertGreater(self.proof['changed_weight_count'],0)
        self.assertGreater(self.proof['weight_delta_l2'],0)
        self.assertLess(self.proof['final_train_loss'],self.proof['initial_train_loss'])
        self.assertTrue(all(math.isfinite(x['gradient_l2']) and x['gradient_l2']>0 for x in self.proof['trace']))

    def test_analytic_gradient_matches_finite_differences(self):
        xs=[{0:0.6,1:0.8},{0:1.0}]; labels=[1,0]
        weights=[[0.2,-0.1],[0.4,0.3]]; bias=[0.1,-0.2]
        _,gradient,gb=objective_gradient(xs,labels,weights,bias)
        epsilon=1e-6
        for c in range(2):
            for i in range(2):
                plus=copy.deepcopy(weights);minus=copy.deepcopy(weights)
                plus[c][i]+=epsilon;minus[c][i]-=epsilon
                numeric=(objective_gradient(xs,labels,plus,bias)[0]-objective_gradient(xs,labels,minus,bias)[0])/(2*epsilon)
                self.assertAlmostEqual(gradient[c][i],numeric,places=8)
            plus=bias[:];minus=bias[:];plus[c]+=epsilon;minus[c]-=epsilon
            numeric=(objective_gradient(xs,labels,weights,plus)[0]-objective_gradient(xs,labels,weights,minus)[0])/(2*epsilon)
            self.assertAlmostEqual(gb[c],numeric,places=8)

    def test_fit_only_receives_training_and_catalogue(self):
        # A fresh training run remains byte-identical when evaluation text is changed.
        data=copy.deepcopy(self.data)
        for split in ('development','heldout'):
            for case in data[split]:case['query']='Unseenonlyxyz '+case['query']
        model,proof=fit(data['train'],data['corpus'])
        self.assertNotIn('unseenonlyxyz',model['vocabulary'])
        self.assertNotIn('antibiotic',model['vocabulary']) # actual heldout-only term
        self.assertEqual(proof,self.proof)
        self.assertEqual(model['weights'],self.model['weights'])

    def test_no_canonical_or_personal_training_admission(self):
        original=json.loads((self.root/'manifest.json').read_text())
        for change in [{'data_kind':'collected_corpus'}, {'contains_personal_data':True},
                       {'canonical_or_scholarly_reviewed':True}, {'schema_version':True}]:
            self.edit('manifest.json',{**original,**change})
            with self.assertRaises(ValueError):load_dataset(self.root)
        self.edit('manifest.json',original)
        corpus=copy.deepcopy(self.data['corpus']);corpus[0]['canonical']=True
        self.edit('corpus.json',corpus)
        with self.assertRaises(ValueError):load_dataset(self.root)

    def test_hash_family_and_normalized_query_leakage_rejected(self):
        (self.root/'heldout.json').write_bytes(b'[]')
        with self.assertRaises(ValueError):load_dataset(self.root)
        for change in [{'family':self.data['train'][0]['family']},
                       {'id':self.data['train'][0]['id']},
                       {'query':'  '+self.data['train'][0]['query'].upper().replace(' ','  ')+' '},
                       {'relevant':['unknown']}, {'relevant':['noninjury','noninjury']}]:
            rows=copy.deepcopy(self.data['heldout']);rows[0].update(change)
            self.edit('heldout.json',rows)
            with self.subTest(change=change),self.assertRaises(ValueError):load_dataset(self.root)

    def test_dataset_limits_and_symlinks(self):
        rows=copy.deepcopy(self.data['heldout']);rows[0]['query']='x'*4097
        self.edit('heldout.json',rows)
        with self.assertRaises(ValueError):load_dataset(self.root)
        self.edit('heldout.json',self.data['heldout'])
        path=self.root/'alias';path.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):load_dataset(path)
        self.edit('train.json',self.data['train']*6)
        with self.assertRaises(ValueError):load_dataset(self.root)

    def test_inert_json_reload_and_reject_parameter_or_catalogue_drift(self):
        path=self.root/'model.json';path.write_bytes(encoded(self.model))
        self.assertEqual(load_model(path,self.data),self.model)
        for change in [{'corpus_sha256':'0'*64}, {'manifest_sha256':'0'*64},
                       {'weights':[[0.0]]}, {'idf':[True]*len(self.model['idf'])},
                       {'thresholds':{'trained':float('nan'),'lexical':1,'tfidf':0.1}},
                       {'ids':list(reversed(self.model['ids']))}, {'vocabulary':['x','x']}]:
            bad={**self.model,**change}
            path.write_text(json.dumps(bad))
            with self.subTest(change=list(change)),self.assertRaises(ValueError):load_model(path,self.data)

    def test_unknown_features_and_metric_denominators(self):
        self.assertEqual(vector('unseenonlyxyz',self.model['vocabulary'],self.model['idf']),{})
        report=evaluate(self.model,self.data['corpus'],self.data['heldout'],'trained',1.0)
        self.assertEqual(report['accepted'],0)
        self.assertIsNone(report['accepted_precision'])
        self.assertEqual(report['negative_rejected'],8)
        self.assertEqual(report['positive_cases'],24)
        self.assertEqual(len(report['cases']),32)
        self.assertEqual(report['cases'][0]['decision_correct'],False)

    def test_cli_consent_new_output_and_fresh_process_reload(self):
        output=self.root/'run'
        command=[sys.executable,str(ROOT/'scripts/train_evidence_router.py'),'--output',str(output)]
        denied=subprocess.run(command,capture_output=True)
        self.assertNotEqual(denied.returncode,0)
        self.assertFalse(output.exists())
        actual=subprocess.run(command+['--confirm-training'],capture_output=True,text=True,timeout=30)
        self.assertEqual(actual.returncode,0,actual.stderr)
        report=json.loads((output/'report.json').read_text())
        marker=json.loads((output/'COMPLETED.json').read_text())
        self.assertTrue(report['reload']['fresh_python_process'])
        self.assertTrue(report['reload']['exact_all_case_scores_rankings_and_decisions'])
        self.assertEqual(marker['model_sha256'],digest((output/'model.json').read_bytes()))
        self.assertEqual(marker['report_sha256'],digest((output/'report.json').read_bytes()))
        repeat=subprocess.run(command+['--confirm-training'],capture_output=True)
        self.assertNotEqual(repeat.returncode,0)
        for file in output.iterdir():self.assertEqual(file.stat().st_mode & 0o777,0o600)
        self.assertEqual(output.stat().st_mode & 0o777,0o700)
        reload=subprocess.run([sys.executable,str(ROOT/'scripts/train_evidence_router.py'),'--reload',str(output/'model.json')],capture_output=True,text=True,timeout=30)
        self.assertEqual(reload.returncode,0,reload.stderr)
        self.assertEqual(json.loads(reload.stdout),report['heldout'])


if __name__=='__main__':unittest.main()
