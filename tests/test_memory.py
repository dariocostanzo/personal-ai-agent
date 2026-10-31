import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import memory


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


if __name__ == "__main__":
    unittest.main()
