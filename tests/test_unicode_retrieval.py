import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from jace.canonical import CanonicalStore
from jace.cognitive_graph import terms
from jace.engine import CognitiveEngine
from jace.text import lexical_terms


class UnicodeRetrievalTests(unittest.TestCase):
    def test_combining_marks_punctuation_and_normalization(self):
        self.assertEqual(lexical_terms("अहिंसा, करुणा। અહિંસા; કરુણા!"),
                         {"अहिंसा", "करुणा", "અહિંસા", "કરુણા"})
        self.assertEqual(lexical_terms(unicodedata.normalize("NFD", "CAFÉ")), {"café"})
        self.assertEqual(terms("अहिंसा અહિંસા"), {"अहिंसा", "અહિંસા"})
        self.assertEqual(terms("THE quiet low-energy _rooms_"), {"the", "quiet", "low-energy", "rooms"})
        self.assertEqual(lexical_terms("123 \u0301 !!!"), set())

    def test_hindi_and_gujarati_memory_graph_remain_user_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = CognitiveEngine(db_path=Path(directory) / "test.sqlite3")
            try:
                hindi, _ = engine.remember("alice", "मुझे शांति और करुणा पसंद है")
                gujarati, _ = engine.remember("alice", "મને શાંતિ અને કરુણા ગમે છે")
                engine.remember("bob", "शांति करुणा શાંતિ કરુણા निजी")
                for query, memory in [("करुणा?", hindi), ("કરુણા?", gujarati)]:
                    hits = engine.search_graph(query, "alice")
                    memory_hits = [hit for hit in hits if hit.node_type == "memory"]
                    self.assertEqual([hit.node_id for hit in memory_hits], [f"memory:{memory.memory_id}"])
                    self.assertEqual([item.memory_id for item in engine.memory.search("alice", query)], [memory.memory_id])
            finally:
                engine.close()

    def test_canonical_exact_unicode_terms_not_substrings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canonical.json"
            records = []
            for index, title in enumerate(["करुणा", "કરુણા", "Apartment", "café"]):
                records.append(dict(entry_id=str(index), title=title, principle=title,
                    guidance="Synthetic fixture", source="Test source", tags=[], work="Test work",
                    language="test", location="test", license="CC0-1.0", verified=True))
            path.write_text(json.dumps(records), encoding="utf-8")
            store = CanonicalStore(path)
            for query in ["करुणा?", "કરુણા?", unicodedata.normalize("NFD", "café")]:
                self.assertEqual(len(store.search(query)), 1)
            self.assertEqual(store.search("art"), [])


if __name__ == "__main__":
    unittest.main()
