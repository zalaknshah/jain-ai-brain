import sqlite3
import tempfile
import unittest
from pathlib import Path

from jace.engine import CognitiveEngine


class MemoryPrivacyTests(unittest.TestCase):
    def test_audit_does_not_duplicate_memory_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            try:
                engine.remember('alice', 'I prefer quiet rooms')
                with sqlite3.connect(path) as connection:
                    content, accepted = connection.execute(
                        'SELECT content, accepted FROM memory_audit WHERE user_id=?', ('alice',)).fetchone()
                self.assertIsNone(content)
                self.assertEqual(accepted, 1)
            finally:
                engine.close()

    def test_forget_erases_historical_audit_and_graph_without_touching_others(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            try:
                memory, _ = engine.remember('alice', 'I prefer gentle movement')
                engine.remember('bob', 'I prefer quiet rooms')
                with sqlite3.connect(path) as connection:
                    connection.execute('UPDATE memory_audit SET content=? WHERE user_id=?',
                                       ('legacy sensitive text', 'alice'))
                self.assertEqual(engine.forget_user('alice'), 1)
                self.assertEqual(engine.forget_user('alice'), 0)
                self.assertEqual(len(engine.memory.list('bob')), 1)
                with sqlite3.connect(path) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit WHERE user_id=?', ('alice',)).fetchone()[0], 0)
                    node = f'memory:{memory.memory_id}'
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_nodes WHERE node_id=?', (node,)).fetchone()[0], 0)
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_edges WHERE from_id=? OR to_id=?', (node,node)).fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_type='canonical'").fetchone()[0], 6)
            finally:
                engine.close()

    def test_forget_removes_only_exact_owned_legacy_orphans(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            try:
                bob, _ = engine.remember('bob', 'I prefer quiet rooms')
                with sqlite3.connect(path) as connection:
                    for node_id, owner in [('memory:9991', 'alice'), ('memory:9992', 'alice-other')]:
                        connection.execute("INSERT INTO graph_nodes(node_id,node_type,title,content,immutable) VALUES (?,'memory',?,?,0)",
                                           (node_id, f'Memory for {owner}', 'historical orphan text'))
                        connection.execute("INSERT INTO graph_edges(from_id,to_id,relation) VALUES (?,'canonical:ahimsa-001','aligned_with')", (node_id,))
                    connection.execute("UPDATE graph_nodes SET title='Memory for alice' WHERE node_id=?", (f'memory:{bob.memory_id}',))
                # Alice has no active memories, so deletion must still clean her orphan.
                self.assertEqual(engine.forget_user('alice'), 0)
                with sqlite3.connect(path) as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_id='memory:9991'").fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_edges WHERE from_id='memory:9991' OR to_id='memory:9991'").fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_id='memory:9992'").fetchone()[0], 1)
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM graph_nodes WHERE node_id=?', (f'memory:{bob.memory_id}',)).fetchone()[0], 1)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_type='canonical'").fetchone()[0], 6)
                self.assertEqual(len(engine.memory.list('bob')), 1)
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
