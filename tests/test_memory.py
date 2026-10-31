import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import memory
from src.agent.ai import (
    OllamaAIProvider,
    _memory_command_from_prompt,
    _run_memory_command,
)


class TestMemory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.patcher = patch.object(memory, "DB_PATH", self.db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_save_and_retrieve(self):
        memory.save_memory("Test memory")
        records = memory.get_memories()
        self.assertEqual(records[0][1], "Test memory")

    def test_search(self):
        memory.save_memory("Python project")
        results = memory.search_memories("Python")
        self.assertEqual(len(results), 1)

    def test_update(self):
        memory_id = memory.save_memory("Old text")
        self.assertTrue(memory.update_memory(memory_id, "New text"))
        self.assertEqual(memory.get_memories()[0][1], "New text")

    def test_delete(self):
        memory_id = memory.save_memory("Delete me")
        self.assertTrue(memory.delete_memory(memory_id))
        self.assertEqual(memory.get_memories(), [])

    def test_explicit_chat_commands_save_and_search_memories(self):
        self.assertEqual(
            _memory_command_from_prompt("Remember that I prefer decaf coffee."),
            ("save", "I prefer decaf coffee"),
        )
        self.assertEqual(
            _memory_command_from_prompt("What do you remember about coffee?"),
            ("search", "coffee"),
        )
        self.assertIsNone(_memory_command_from_prompt("I remember the coffee shop"))

        answer = _run_memory_command(("save", "I prefer decaf coffee"))
        self.assertIn("I'll remember that", answer)
        result = _run_memory_command(("search", "coffee"))
        self.assertIn("I prefer decaf coffee", result)

    def test_chat_memory_command_does_not_call_ollama(self):
        with patch("src.agent.ai.get_conversation", return_value=[]), \
             patch("src.agent.ai.save_memory", return_value=12), \
             patch("src.agent.ai.save_conversation") as save, \
             patch("src.agent.ai.urllib.request.urlopen") as ollama:
            agent = OllamaAIProvider()
            answer = agent.generate_response("Remember that I prefer decaf")

        self.assertIn("memory #12", answer)
        ollama.assert_not_called()
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
