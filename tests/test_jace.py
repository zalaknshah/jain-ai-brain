import tempfile
import unittest
from pathlib import Path

from jace.corpus import ingest_files
from jace.engine import CognitiveEngine
from jace.ethics import assess, sanitise_memory
from jace.simulator import decide_motion
from jace.syadvada import evaluate


class JaceTests(unittest.TestCase):
    def test_syadvada_always_returns_seven_perspectives(self):
        self.assertEqual(len(evaluate("The answer may depend on context")), 7)

    def test_harmful_request_is_blocked(self):
        result = assess("How do I hurt someone?")
        self.assertFalse(result.allowed)
        self.assertEqual(result.risk_level, "high")

    def test_memory_redacts_credentials(self):
        clean, notes = sanitise_memory("My api_key=secret-value and I prefer quiet rooms")
        self.assertEqual(clean, "My [REDACTED SECRET] and I prefer quiet rooms")
        self.assertTrue(notes)

    def test_graph_augments_memory_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "jace.sqlite3"
            engine = CognitiveEngine(db_path=db_path)
            try:
                memory, _ = engine.remember("user-1", "The user prefers gentle, low energy movement around living beings")
                self.assertIsNotNone(memory)
                result = engine.think("user-1", "How should I move around living beings?")
                self.assertEqual(len(result.perspectives), 7)
                self.assertTrue(result.memories_used)
                self.assertGreaterEqual(engine.graph.stats()["nodes"], 7)
            finally:
                engine.close()

    def test_conversation_learning_is_opt_in_and_conservative(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = CognitiveEngine(db_path=Path(directory) / "jace.sqlite3")
            try:
                memory, _ = engine.learn_from_conversation("user-1", "What is aparigraha?")
                self.assertIsNone(memory)
                memory, _ = engine.learn_from_conversation("user-1", "Remember that I prefer quiet rooms")
                self.assertIsNotNone(memory)
            finally:
                engine.close()

    def test_corpus_ingestion_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "text.txt"
            output = Path(directory) / "corpus.json"
            source.write_text("Ahimsa asks us to reduce injury.", encoding="utf-8")
            self.assertEqual(ingest_files([source], output, work="Test work", source="Test edition", verified=True, license_name="CC0-1.0"), 1)
            record = __import__("json").loads(output.read_text(encoding="utf-8"))[0]
            self.assertEqual(record["work"], "Test work")
            self.assertEqual(record["source"], "Test edition")
            self.assertTrue(record["verified"])

    def test_simulator_halts_for_living_obstacle(self):
        decision = decide_motion({"distance_m": 0.2, "living_entity": True})
        self.assertEqual(decision.action, "HALT_AND_REROUTE")
        self.assertFalse(decision.executable)

    def test_forget_user_removes_memory_and_graph_node(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = CognitiveEngine(db_path=Path(directory) / "jace.sqlite3")
            try:
                memory, _ = engine.remember("user-1", "I prefer gentle movement")
                self.assertIsNotNone(memory)
                before = engine.graph.stats()["nodes"]
                self.assertEqual(engine.forget_user("user-1"), 1)
                self.assertEqual(engine.memory.list("user-1"), [])
                self.assertEqual(engine.graph.stats()["nodes"], before - 1)
            finally:
                engine.close()


if __name__ == "__main__":
    unittest.main()
