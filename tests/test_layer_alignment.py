import copy
import hashlib
import unittest
from scripts.prepare_layer_alignment import prepare_layers


class LayerAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.source = 'मूल\nmeaning\nnote'.encode()
        self.spec = {'source_sha256': hashlib.sha256(self.source).hexdigest(),
            'metadata': {key: 'synthetic' for key in ('work', 'edition', 'source_url', 'rights_basis', 'rights_notice', 'attribution', 'locator')},
            'layers': [
                dict(id='r', byte_start=0, byte_end=9, locator='1', language='und', role='root', family='verse1', root_id=None),
                dict(id='t', byte_start=10, byte_end=17, locator='2', language='en', role='translation', family='verse1', root_id='r'),
                dict(id='c', byte_start=18, byte_end=22, locator='3', language='en', role='commentary', family='verse1', root_id='r')]}

    def test_separate_languages_roles_and_closed_gates(self):
        result = prepare_layers(self.source, self.spec)
        self.assertEqual([t['source_text'] for t in result['tasks']], ['मूल', 'meaning', 'note'])
        self.assertEqual(result['tasks'][0]['source']['metadata']['declared_source_language'], 'und')
        for task in result['tasks']:
            self.assertEqual(task['alignment']['status'], 'unreviewed')
            self.assertTrue(all(t['draft'] is None for t in task['translations'].values()))
        self.assertFalse(result['training_admitted'])
        self.assertFalse(result['runtime_admitted'])
        self.assertFalse(result['public_release_approved'])

    def test_deterministic_and_unaliased(self):
        result = prepare_layers(self.source, self.spec)
        self.assertEqual(result, prepare_layers(self.source, self.spec))
        saved = copy.deepcopy(result)
        self.spec['metadata']['work'] = 'changed'
        self.spec['layers'][0]['family'] = 'changed'
        self.assertEqual(result, saved)

    def test_link_binding_covers_root_content(self):
        before = prepare_layers(self.source, self.spec)
        source = self.source.replace('मूल'.encode(), 'धूल'.encode())
        self.spec['source_sha256'] = hashlib.sha256(source).hexdigest()
        after = prepare_layers(source, self.spec)
        self.assertNotEqual(before['tasks'][1]['alignment_binding_sha256'], after['tasks'][1]['alignment_binding_sha256'])

    def test_rejects_bad_links_and_ranges(self):
        cases = [('root_id', 'missing'), ('root_id', 't'), ('family', 'other'), ('byte_start', 8), ('byte_start', True), ('role', 'verified'), ('language', '')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                spec = copy.deepcopy(self.spec)
                spec['layers'][1][key] = value
                with self.assertRaises(ValueError):
                    prepare_layers(self.source, spec)

    def test_rejects_root_link_duplicate_and_digest_drift(self):
        for change in ('root_link', 'duplicate', 'digest', 'cut_character', 'approval'):
            with self.subTest(change=change):
                spec = copy.deepcopy(self.spec)
                if change == 'root_link': spec['layers'][0]['root_id'] = 'r'
                if change == 'duplicate': spec['layers'][1]['id'] = 'r'
                if change == 'digest': spec['source_sha256'] = '0'*64
                if change == 'cut_character': spec['layers'][0]['byte_end'] = 8
                if change == 'approval': spec['training_admitted'] = True
                with self.assertRaises(ValueError): prepare_layers(self.source, spec)

    def test_forward_root_link(self):
        self.spec['layers'].reverse()
        self.assertEqual(len(prepare_layers(self.source, self.spec)['tasks']), 3)

    def test_valid_utf8_overlap_and_adjacent_ranges(self):
        self.spec['layers'][2]['byte_start'] = 16
        with self.assertRaisesRegex(ValueError, 'overlap'):
            prepare_layers(self.source, self.spec)
        self.spec['layers'][2]['byte_start'] = 17
        result = prepare_layers(self.source, self.spec)
        self.assertEqual(result['tasks'][2]['source_text'], '\nnote')
