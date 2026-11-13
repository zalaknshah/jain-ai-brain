import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from jace.evidence_router import digest, load_dataset

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('router_challenge', ROOT / 'scripts/evaluate_router_challenge.py')
challenge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(challenge)


class RouterChallengeTests(unittest.TestCase):
    def setUp(self):
        self.data = load_dataset(ROOT / 'training/evidence_router')
        self.rows = [{'id': 'new-positive', 'family': 'new', 'query': 'Synthetic new query for a passage location?', 'relevant': ['provenance']},
                     {'id': 'new-negative', 'family': 'new', 'query': 'Synthetic unrelated calculator query?', 'relevant': []}]

    def inspect(self, rows=None, sha=None):
        raw = json.dumps(self.rows if rows is None else rows).encode()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'challenge.json'; p.write_bytes(raw)
            return challenge.inspect_challenge(p, sha or digest(raw), self.data)

    def test_valid_original_challenge(self):
        self.assertEqual(self.inspect(), self.rows)

    def test_hash_mismatch(self):
        with self.assertRaises(ValueError): self.inspect(sha='0' * 64)

    def test_exposed_query_rejected_for_every_split(self):
        for split in ('train', 'development', 'heldout'):
            rows = copy.deepcopy(self.rows)
            rows[0]['query'] = '  ' + self.data[split][0]['query'].upper() + '  '
            with self.assertRaises(ValueError): self.inspect(rows)

    def test_duplicates_rejected(self):
        for field in ('id', 'query'):
            rows = copy.deepcopy(self.rows); rows[1][field] = rows[0][field]
            with self.assertRaises(ValueError): self.inspect(rows)

    def test_requires_positive_and_negative(self):
        for labels in ([], ['consent']):
            rows = copy.deepcopy(self.rows)
            for row in rows: row['relevant'] = labels
            with self.assertRaises(ValueError): self.inspect(rows)

    def test_invalid_labels_and_schema(self):
        for labels in (None, ['other'], ['consent', 'consent'], [False]):
            rows = copy.deepcopy(self.rows); rows[0]['relevant'] = labels
            with self.assertRaises(ValueError): self.inspect(rows)
        rows = copy.deepcopy(self.rows); rows[0]['extra'] = True
        with self.assertRaises(ValueError): self.inspect(rows)

    def test_real_training_reload_and_challenge_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = root / 'model'
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/train_evidence_router.py'),
                                  '--confirm-training', '--output', str(model_dir)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            p = root / 'challenge.json'
            raw = json.dumps(self.rows).encode(); p.write_bytes(raw)
            command = [sys.executable, str(ROOT / 'scripts/evaluate_router_challenge.py'),
                       '--model', str(model_dir / 'model.json'), '--challenge', str(p),
                       '--challenge-sha256', digest(raw)]
            first = subprocess.run(command, capture_output=True, text=True)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            report = json.loads(first.stdout)
            self.assertEqual(report['case_count'], 2)
            self.assertFalse(report['training_started'])
            self.assertFalse(report['thresholds_retuned'])
            self.assertFalse(report['runtime_admitted'])
            self.assertEqual(set(report['results']), {'lexical', 'tfidf', 'trained'})
            p.write_bytes(raw + b' ')
            failed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(set(root.iterdir()), {p, model_dir})

    def test_invalid_size(self):
        for rows in ([], self.rows[:1], self.rows * 129):
            with self.assertRaises(ValueError): self.inspect(rows)


if __name__ == '__main__': unittest.main()
