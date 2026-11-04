import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from jace.engine import CognitiveEngine
from jace.reasoner import LocalReasoner
from jace import retrieval_limits as limits

ROOT = Path(__file__).resolve().parents[1]


class RetrievalReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = CognitiveEngine(Path(self.temp.name)/'memory.db', ROOT/'evals/retrieval/corpus.json', LocalReasoner())

    def tearDown(self):
        self.engine.close(); self.temp.cleanup()

    def remember(self, content, **kwargs):
        return self.engine.remember('alice', content, **kwargs)[0]

    def test_old_direct_and_graph_matches_survive_newer_unrelated_memories(self):
        old = self.remember('I prefer cobalt reservation')
        for index in range(110):
            self.remember(f'I prefer quiet music number {index}')
        self.assertEqual(self.engine.memory.search('alice', 'reservation'), [old])
        self.assertEqual(self.engine.think('alice', 'reservation').memories_used, [old])
        self.assertEqual(self.engine.think('alice', 'lantern').memories_used, [old])

    def test_direct_rank_and_short_tokens_survive_graph_supplement(self):
        strong = self.remember('I prefer cobalt amber lenses')
        weak = self.remember('I prefer cobalt')
        self.assertEqual(self.engine.think('alice', 'cobalt amber').memories_used[:2], [strong, weak])
        red = self.remember('I prefer red')
        ai = self.remember('I prefer AI')
        self.assertEqual(self.engine.think('alice', 'AI red').memories_used, [ai, red])

    def test_top_k_is_bounded_with_recency_ties_and_no_term_fallback(self):
        memories = [self.remember(f'I prefer quiet music {index}') for index in range(15)]
        for query in ('quiet', '12345'):
            self.assertEqual(self.engine.memory.search('alice', query, limit=3), list(reversed(memories[-3:])))
        for value in (0, -1, 101, True, 1.5):
            with self.subTest(limit=value), self.assertRaises(ValueError):
                self.engine.memory.search('alice', 'quiet', limit=value)

    def test_selected_graph_ids_cannot_override_owner_scope_or_expiry(self):
        home = self.remember('I prefer home', memory_scope='home')
        work = self.remember('I prefer work', memory_scope='work')
        expired = self.remember('I prefer old', memory_scope='home', expires_at='2000-01-01T00:00:00Z')
        bob = self.engine.remember('bob', 'I prefer private', memory_scope='home')[0]
        ids = [bob.memory_id, work.memory_id, expired.memory_id, home.memory_id, home.memory_id]
        self.assertEqual(self.engine.memory.selected('alice', ids, memory_scope='home'), [home])
        self.engine.memory.connection.execute('UPDATE memories SET expires_at = ? WHERE id = ?', ('invalid', home.memory_id))
        self.engine.memory.connection.commit()
        self.assertEqual(self.engine.memory.selected('alice', ids, memory_scope='home'), [])
        for invalid in ([True], [0], [-1], [2**63], ['1'], list(range(1, 102)), None):
            with self.subTest(ids=invalid), self.assertRaises(ValueError):
                self.engine.memory.selected('alice', invalid)

    def test_row_byte_and_query_budgets_fail_without_partial_context_or_model_calls(self):
        self.remember('I prefer quiet rooms'); self.remember('I prefer music')
        reasoner = Mock(); self.engine.reasoner = reasoner
        for name, value in [('MAX_SCAN_ROWS', 1), ('MAX_SCAN_BYTES', 3)]:
            with self.subTest(name=name), patch.object(limits, name, value):
                for call in (lambda:self.engine.memory.search('alice','quiet'), lambda:self.engine.think('alice','quiet')):
                    with self.assertRaisesRegex(ValueError, 'budget'): call()
        reasoner.respond.assert_not_called()
        self.assertEqual(len(self.engine.list_memories('alice')), 2)
        query = ' '.join(f'word{index}' for index in range(257))
        for call in (lambda:self.engine.memory.search('alice',query), lambda:self.engine.canonical.search(query),
                     lambda:self.engine.search_graph(query,'alice')):
            with self.assertRaisesRegex(ValueError,'term budget'):call()
        for query in ('x'*10001, None):
            with self.assertRaises(ValueError): self.engine.memory.search('alice',query)

    def test_new_oversized_memory_rejected_before_persistence_and_old_record_fails_closed(self):
        memory = self.remember('I prefer quiet')
        for call in (lambda:self.remember('x'*10001), lambda:self.engine.correct_memory('alice',memory.memory_id,'x'*10001)):
            with self.assertRaises(ValueError): call()
        self.assertEqual(self.engine.list_memories('alice'), [memory])
        self.assertEqual(self.engine.memory.connection.execute('SELECT COUNT(*) FROM memory_audit').fetchone()[0],1)
        self.engine.memory.connection.execute('UPDATE memories SET content = ? WHERE id = ?', ('x'*32769,memory.memory_id))
        with self.assertRaisesRegex(ValueError,'text size budget'):self.engine.memory.search('alice','quiet')

    def test_graph_keeps_strongest_same_depth_path_regardless_of_edge_order(self):
        target=self.remember('I prefer music')
        connection=self.engine.memory.connection
        nodes=self.engine.graph._canonical_node_ids
        for reverse in (False,True):
            connection.execute('DELETE FROM graph_edges')
            edges=[(nodes['fixture-lantern'],f'memory:{target.memory_id}','test',0.1),
                   (nodes['fixture-garden'],f'memory:{target.memory_id}','test',0.9)]
            connection.executemany('INSERT INTO graph_edges VALUES (?,?,?,?)',list(reversed(edges)) if reverse else edges)
            connection.commit()
            hits=self.engine.search_graph('lantern garden','alice')
            hit=next(item for item in hits if item.node_id==f'memory:{target.memory_id}')
            self.assertAlmostEqual(hit.score,0.25*0.9*0.7)
            self.assertEqual(hit.depth,1)

    def test_graph_edge_budget_and_hop_limits_fail_closed(self):
        self.remember('I prefer cobalt')
        with patch.object(limits,'MAX_EDGE_ROWS',0),self.assertRaisesRegex(ValueError,'edge row budget'):
            self.engine.search_graph('lantern','alice')
        for value in (-1,3,True,1.2):
            with self.subTest(hops=value),self.assertRaises(ValueError):
                self.engine.graph.retrieve('lantern','alice',max_hops=value)
        self.assertTrue(self.engine.graph.retrieve('lantern','alice',max_hops=0))

    def test_historical_corpora_do_not_consume_active_graph_row_budget(self):
        connection=self.engine.memory.connection
        for i in range(20):
            connection.execute("INSERT INTO graph_nodes(node_id,node_type,title,content,source_id,immutable) VALUES (?, 'canonical','old','lantern','old',1)",(f'canonical:old:{i}',))
        connection.commit()
        with patch.object(limits,'MAX_SCAN_ROWS',3):
            self.assertEqual([hit.source_id for hit in self.engine.search_graph('lantern','alice')],['fixture-lantern'])

    def test_synthetic_evaluation_and_metric_arithmetic(self):
        spec=importlib.util.spec_from_file_location('retrieval_eval',ROOT/'scripts/evaluate_retrieval.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        metrics=module.ranking_metrics(['x','a'],['a','b'])
        self.assertEqual(metrics['recall_at_k'],.5);self.assertEqual(metrics['reciprocal_rank_at_k'],.5)
        self.assertIsNone(module.ranking_metrics([],[])['recall_at_k'])
        self.assertFalse(module.ranking_metrics(['x'],[])['empty_label_correct'])
        with self.assertRaises(ValueError):module.ranking_metrics(['a','a'],['a'])
        result=module.run()
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['case_count'],10)
        self.assertEqual(result['aggregate']['memory']['mean_recall_at_5'],1.0)


if __name__=='__main__':unittest.main()
