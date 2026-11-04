import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.engine import CognitiveEngine


class AtomicMemoryTests(unittest.TestCase):
    def counts(self, path):
        with sqlite3.connect(path) as connection:
            return tuple(connection.execute(query).fetchone()[0] for query in [
                'SELECT COUNT(*) FROM memories',
                'SELECT COUNT(*) FROM memory_audit',
                "SELECT COUNT(*) FROM graph_nodes WHERE node_type='memory'",
            ])

    def test_remember_rolls_back_if_graph_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            original = engine.graph.add_memory
            def fail_after_write(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError('injected failure')
            try:
                with patch.object(engine.graph, 'add_memory', side_effect=fail_after_write):
                    with self.assertRaises(RuntimeError):
                        engine.remember('alice', 'I prefer quiet rooms')
                self.assertEqual(self.counts(path), (0, 0, 0))
            finally:
                engine.close()

    def test_forget_rolls_back_all_stores_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            engine.remember('alice', 'I prefer quiet rooms')
            original = engine.memory.delete_user
            def fail_after_write(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError('injected failure after all deletions')
            try:
                with patch.object(engine.memory, 'delete_user', side_effect=fail_after_write):
                    with self.assertRaises(RuntimeError):
                        engine.forget_user('alice')
                self.assertEqual(self.counts(path), (1, 1, 1))
                self.assertEqual(engine.forget_user('alice'), 1)
                self.assertEqual(self.counts(path), (0, 0, 0))
            finally:
                engine.close()

    def concurrent_forget_and_remember(self, separate_engine):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'memory.db'
            engine = CognitiveEngine(db_path=path)
            other = CognitiveEngine(db_path=path) if separate_engine else engine
            engine.remember('alice', 'I prefer quiet rooms')
            snapshot_taken = threading.Event()
            resume_forget = threading.Event()
            writer_started = threading.Event()
            writer_done = threading.Event()
            errors = []
            results = {}
            original_list = engine.memory.list
            def pause_after_snapshot(*args, **kwargs):
                result = original_list(*args, **kwargs)
                snapshot_taken.set()
                if not resume_forget.wait(3):
                    raise RuntimeError('test coordination timeout')
                return result
            def forget():
                try:
                    results['deleted'] = engine.forget_user('alice')
                except Exception as error:
                    errors.append(error)
            def remember():
                writer_started.set()
                try:
                    results['new'], _ = other.remember('alice', 'I prefer confidential green cloth')
                except Exception as error:
                    errors.append(error)
                finally:
                    writer_done.set()
            first = threading.Thread(target=forget)
            second = threading.Thread(target=remember)
            try:
                with patch.object(engine.memory, 'list', side_effect=pause_after_snapshot):
                    first.start()
                    self.assertTrue(snapshot_taken.wait(2))
                    second.start()
                    self.assertTrue(writer_started.wait(2))
                    # Writer may start, but cannot commit inside forget's transaction.
                    self.assertFalse(writer_done.wait(0.1))
                    resume_forget.set()
                    first.join(3)
                    second.join(3)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(results['deleted'], 1)
                self.assertEqual(self.counts(path), (1, 1, 1))
                with sqlite3.connect(path) as connection:
                    orphans = connection.execute("SELECT COUNT(*) FROM graph_nodes g LEFT JOIN memories m ON g.node_id='memory:' || m.id WHERE g.node_type='memory' AND m.id IS NULL").fetchone()[0]
                self.assertEqual(orphans, 0)
                self.assertEqual(engine.forget_user('alice'), 1)
                self.assertEqual(self.counts(path), (0, 0, 0))
            finally:
                resume_forget.set()
                if first.ident:
                    first.join(3)
                if second.ident:
                    second.join(3)
                if other is not engine:
                    other.close()
                engine.close()

    def test_one_engine_serializes_forget_and_remember(self):
        self.concurrent_forget_and_remember(False)

    def test_separate_engines_share_sqlite_writer_boundary(self):
        self.concurrent_forget_and_remember(True)


if __name__ == '__main__':
    unittest.main()
