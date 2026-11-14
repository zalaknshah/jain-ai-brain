import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner
from jace.retrieval_limits import query_terms


class QueryExpansionBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = CognitiveEngine(Path(self.temp.name) / 'db', reasoner=LocalReasoner())
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.engine.close)

    def test_full_user_query_preserved_when_expansion_exceeds_character_limit(self):
        request = ('clean room ' * 909).strip()
        self.assertEqual(len(request), 9998)
        with patch.object(self.engine.canonical, 'search', wraps=self.engine.canonical.search) as search:
            result = self.engine.think('synthetic', request)
            self.assertEqual(result.input, request)
            search.assert_called_once_with(request, limit=5)

    def test_full_user_query_preserved_when_expansion_exceeds_term_limit(self):
        request = 'clean room ' + ' '.join(f'word{i}' for i in range(254))
        self.assertEqual(len(query_terms(request)), 256)
        with patch.object(self.engine.canonical, 'search', wraps=self.engine.canonical.search) as search:
            preview = self.engine.preview_context('synthetic', request)
            self.assertFalse(preview['blocked'])
            search.assert_called_once_with(request, limit=5)

    def test_ordinary_authored_expansion_still_applies(self):
        with patch.object(self.engine.canonical, 'search', wraps=self.engine.canonical.search) as search:
            self.engine.think('synthetic', 'clean room')
            self.assertTrue(search.call_args.args[0].startswith('clean room '))
            self.assertIn('ahimsa', search.call_args.args[0])

    def test_invalid_original_query_still_rejected_before_canonical_search(self):
        for request in ('clean room ' + 'x'*10000, 'clean room ' + ' '.join(f'word{i}' for i in range(255))):
            with self.subTest(chars=len(request)), patch.object(self.engine.canonical, 'search') as search:
                with self.assertRaises(ValueError):
                    self.engine.think('synthetic', request)
                search.assert_not_called()
