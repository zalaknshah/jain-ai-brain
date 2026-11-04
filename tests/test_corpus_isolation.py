import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.canonical import CanonicalStore
from jace.engine import CognitiveEngine


def corpus(path, *pairs):
    path.write_text(json.dumps([dict(entry_id=key, title=text, principle=text,
        guidance="Synthetic reviewed fixture", source="Test source", tags=[text],
        work="Test work", language="en", location="test", license="CC0-1.0", verified=True)
        for key, text in pairs]), encoding="utf-8")
    return path


class CorpusIsolationTests(unittest.TestCase):
    def test_startup_binds_only_admitted_corpus_preserving_memories_and_legacy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "db.sqlite3"
            old = CognitiveEngine(db_path=db)
            saved, _ = old.remember("alice", "I prefer quiet rooms")
            # Pre-namespace node as written by earlier released versions.
            old.memory.connection.execute("INSERT INTO graph_nodes(node_id,node_type,title,content,immutable) VALUES ('canonical:legacy','canonical','Legacy','legacysecret',1)")
            old.memory.connection.commit()
            before = old.graph.stats()
            old.close()
            new = CognitiveEngine(db_path=db, canonical_path=corpus(root / "new.json", ("reviewed1", "newphrase")))
            try:
                self.assertEqual(new.search_graph("Ahimsa", "alice"), [])
                self.assertEqual(new.search_graph("legacysecret", "alice"), [])
                self.assertEqual([hit.source_id for hit in new.search_graph("newphrase", "alice")], ["reviewed1"])
                self.assertEqual(new.list_memories("alice")[0].memory_id, saved.memory_id)
                self.assertTrue(new.search_graph("quiet", "alice"))
                self.assertGreater(new.graph.stats()["nodes"], before["nodes"])
            finally:
                new.close()

    def test_same_id_changed_and_removed_content_isolated_between_live_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = CognitiveEngine(db_path=root / "db", canonical_path=corpus(root / "a.json", ("shared", "oldword"), ("removed", "removedword")))
            second = CognitiveEngine(db_path=root / "db", canonical_path=corpus(root / "b.json", ("shared", "newword")))
            try:
                first.remember("alice", "I prefer oldword")
                second.remember("bob", "I prefer newword")
                for engine, own, other in [(first, "oldword", "newword"), (second, "newword", "oldword")]:
                    hits = engine.search_graph(own, "nobody")
                    self.assertEqual(len(hits), 1)
                    self.assertIn(own, hits[0].content)
                    self.assertEqual(engine.search_graph(other, "nobody"), [])
                self.assertTrue(first.search_graph("removedword", "nobody"))
                self.assertEqual(second.search_graph("removedword", "nobody"), [])
                self.assertFalse(any(h.node_type == "canonical" for h in second.search_graph("oldword", "alice")))
            finally:
                first.close()
                second.close()

    def test_failed_rebind_rolls_back_nodes_edges_and_active_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = CognitiveEngine(db_path=root / "db")
            try:
                before = engine.graph.stats()
                ids = dict(engine.graph._canonical_node_ids)
                entries = CanonicalStore(corpus(root / "new.json", ("new", "newword"))).all()
                original = engine.graph._seed_canonical
                def fail_after_writes(*args):
                    original(*args)
                    raise RuntimeError("injected interruption")
                with patch.object(engine.graph, "_seed_canonical", side_effect=fail_after_writes):
                    with self.assertRaises(RuntimeError):
                        engine.graph.seed_canonical(entries)
                self.assertEqual(engine.graph.stats(), before)
                self.assertEqual(engine.graph._canonical_node_ids, ids)
                self.assertTrue(engine.search_graph("Ahimsa", "alice"))
                self.assertEqual(engine.search_graph("newword", "alice"), [])
            finally:
                engine.close()

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = corpus(Path(directory) / "a.json", ("same", "first"), ("same", "second"))
            with self.assertRaises(ValueError):
                CanonicalStore(path)
