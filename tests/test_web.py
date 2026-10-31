import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import conversations
from src.agent.web import ChatHandler


class FakeRequestHandler:
    def __init__(self, path):
        self.path = path
        self.status = None
        self.error_status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    def send_error(self, status):
        self.error_status = status

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestWebHandler(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        patcher = patch.object(
            conversations,
            "CONVERSATIONS_FILE",
            Path(temp_dir.name) / "conversations.json",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, path):
        handler = FakeRequestHandler(path)
        ChatHandler.do_GET(handler)
        return handler

    def test_root_page_accepts_query_parameters(self):
        handler = self.get("/?source=tablet")

        self.assertEqual(handler.status, 200)
        self.assertIsNone(handler.error_status)
        page = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("Personal AI Assistant", page)
        self.assertIn("What should I do today?", page)
        self.assertIn("Find documents about the fridge warranty", page)

    def test_list_saved_conversations(self):
        conversations.save_conversation(
            "chat-1",
            [
                {"role": "user", "content": "Help with my personal agent"},
                {"role": "assistant", "content": "Sure"},
            ],
        )

        handler = self.get("/api/conversations?source=tablet")
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

        self.assertEqual(handler.status, 200)
        self.assertEqual(
            payload["conversations"],
            [{"id": "chat-1", "label": "Help with my personal agent"}],
        )

    def test_load_saved_conversation(self):
        history = [
            {"role": "user", "content": "Help with my personal agent"},
            {"role": "assistant", "content": "Sure"},
        ]
        conversations.save_conversation("chat one", history)

        handler = self.get("/api/conversations/chat%20one")
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

        self.assertEqual(handler.status, 200)
        self.assertEqual(payload, {"id": "chat one", "history": history})

    def test_missing_conversation_returns_404(self):
        handler = self.get("/api/conversations/missing-chat")

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(handler.status, 404)
        self.assertEqual(payload, {"error": "Conversation not found"})


if __name__ == "__main__":
    unittest.main()
