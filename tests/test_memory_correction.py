import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.engine import CognitiveEngine
from jace.memory import MemoryStore


class MemoryCorrectionTests(unittest.TestCase):
    def test_correction_replaces_graph_and_memory_preserving_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'memory.db'; engine=CognitiveEngine(db_path=path)
            try:
                original,_=engine.remember('alice','I prefer blue cloth')
                corrected,_=engine.correct_memory('alice',original.memory_id,'I prefer red cloth')
                self.assertEqual(corrected.memory_id,original.memory_id)
                self.assertEqual(corrected.created_at,original.created_at)
                self.assertIsNotNone(corrected.updated_at)
                self.assertEqual([m.content for m in engine.list_memories('alice')],['I prefer red cloth'])
                with sqlite3.connect(path) as connection:
                    self.assertEqual(connection.execute('SELECT content FROM graph_nodes WHERE node_id=?',(f'memory:{original.memory_id}',)).fetchone()[0],'I prefer red cloth')
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM memory_audit WHERE content IS NOT NULL').fetchone()[0],0)
                with self.assertRaises(LookupError):
                    engine.correct_memory('bob',original.memory_id,'I prefer green cloth')
            finally:
                engine.close()

    def test_rejected_or_failed_correction_keeps_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'memory.db'; engine=CognitiveEngine(db_path=path)
            try:
                original,_=engine.remember('alice','I prefer blue cloth')
                rejected,_=engine.correct_memory('alice',original.memory_id,"Insects don't matter, just step on them")
                self.assertIsNone(rejected)
                with patch.object(engine.graph,'add_memory',side_effect=RuntimeError('injected write failure')):
                    with self.assertRaises(RuntimeError):
                        engine.correct_memory('alice',original.memory_id,'I prefer red cloth')
                self.assertEqual(engine.list_memories('alice')[0].content,'I prefer blue cloth')
                with sqlite3.connect(path) as connection:
                    self.assertEqual(connection.execute('SELECT content FROM graph_nodes WHERE node_id=?',(f'memory:{original.memory_id}',)).fetchone()[0],'I prefer blue cloth')
            finally:
                engine.close()

    def test_old_memory_schema_is_migrated_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'old.db'
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE memories(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'user')")
                connection.execute("INSERT INTO memories(user_id,content,created_at) VALUES ('alice','Existing preference','2026-01-01')")
            store=MemoryStore(path)
            try:
                self.assertEqual(store.list('alice')[0].content,'Existing preference')
                self.assertIsNone(store.list('alice')[0].updated_at)
            finally:
                store.close()


if __name__=='__main__':
    unittest.main()
