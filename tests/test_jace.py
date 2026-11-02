import tempfile
import unittest
from pathlib import Path

from jace.engine import CognitiveEngine
from jace.ethics import assess, sanitise_memory
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


if __name__ == "__main__":
    unittest.main()
