import json
import tempfile
import unittest
from pathlib import Path

from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner


class CanonicalEdgeWeightTests(unittest.TestCase):
    def fixture(self, root, count):
        path = root / 'corpus.json'
        path.write_text(json.dumps([
            dict(entry_id=identifier, title=word, principle=word,
                 guidance='Synthetic fixture', source='Invented test source',
                 tags=[f'topic{i}' for i in range(count)], work='Test work',
                 language='en', location='test', license='CC0-1.0', verified=True)
            for identifier, word in [('left', 'cobalt'), ('right', 'lantern')]
        ]))
        return path

    def test_admitted_shared_tag_counts_have_bounded_retrievable_edges(self):
        for count in (1, 5, 6, 32):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                engine = CognitiveEngine(root / 'db', self.fixture(root, count), LocalReasoner())
                try:
                    weights = [row[0] for row in engine.memory.connection.execute('SELECT weight FROM graph_edges')]
                    self.assertEqual(weights, [min(1.0, 0.5 + 0.1 * count)] * 2)
                    hits = engine.search_graph('cobalt', 'alice')
                    neighbour = next(hit for hit in hits if hit.source_id == 'right')
                    self.assertEqual(neighbour.depth, 1)
                    self.assertLessEqual(neighbour.score, 0.25 * 0.7)
                    engine.think('alice', 'cobalt')
                finally:
                    engine.close()

    def test_restart_repairs_only_old_generated_overflow_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = self.fixture(root, 6)
            engine = CognitiveEngine(root / 'db', corpus, LocalReasoner())
            engine.memory.connection.execute("UPDATE graph_edges SET weight=1.1 WHERE relation='related_principle'")
            ids = engine.graph._canonical_node_ids
            engine.memory.connection.execute("INSERT INTO graph_edges VALUES (?,?,'custom',1.1)", (ids['left'], ids['right']))
            engine.memory.connection.execute("INSERT INTO graph_edges VALUES ('canonical:other:a','canonical:other:b','related_principle',1.1)")
            engine.memory.connection.commit()
            engine.close()
            reopened = CognitiveEngine(root / 'db', corpus, LocalReasoner())
            try:
                self.assertEqual([row[0] for row in reopened.memory.connection.execute("SELECT weight FROM graph_edges WHERE from_id LIKE ? AND relation='related_principle'", (reopened.graph._canonical_prefix + '%',))], [1.0, 1.0])
                self.assertEqual(reopened.memory.connection.execute("SELECT weight FROM graph_edges WHERE relation='custom'").fetchone()[0], 1.1)
                self.assertEqual(reopened.memory.connection.execute("SELECT weight FROM graph_edges WHERE from_id='canonical:other:a'").fetchone()[0], 1.1)
                # Unrelated custom corruption is not silently blessed by repair.
                with self.assertRaisesRegex(ValueError, 'edge weight'):
                    reopened.search_graph('cobalt', 'alice')
                reopened.memory.connection.execute("DELETE FROM graph_edges WHERE relation='custom'")
                self.assertTrue(reopened.search_graph('cobalt', 'alice'))
            finally:
                reopened.close()

    def test_unexpected_bad_weight_still_fails_closed_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = self.fixture(root, 6)
            engine = CognitiveEngine(root / 'db', corpus, LocalReasoner())
            engine.memory.connection.execute('UPDATE graph_edges SET weight=2.5')
            engine.memory.connection.commit()
            engine.close()
            reopened = CognitiveEngine(root / 'db', corpus, LocalReasoner())
            try:
                with self.assertRaisesRegex(ValueError, 'edge weight'):
                    reopened.search_graph('cobalt', 'alice')
            finally:
                reopened.close()
