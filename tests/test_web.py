import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import conversations, goals, memory, recommendations, sessions, tasks
from src.agent.web import ChatHandler


class FakeRequestHandler:
    def __init__(self, path, body=None):
        self.path = path
        self.status = None
        self.error_status = None
        request_body = json.dumps(body).encode("utf-8") if body is not None else b""
        self.headers = {"Content-Length": str(len(request_body))}
        self.rfile = io.BytesIO(request_body)
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
        for module in (goals, memory, recommendations, sessions, tasks):
            patcher = patch.object(module, "DB_PATH", Path(temp_dir.name) / f"{module.__name__}.db")
            patcher.start()
            self.addCleanup(patcher.stop)

    def get(self, path):
        handler = FakeRequestHandler(path)
        ChatHandler.do_GET(handler)
        return handler

    def post(self, path, body):
        handler = FakeRequestHandler(path, body)
        ChatHandler.do_POST(handler)
        return handler

    def test_root_page_accepts_query_parameters(self):
        handler = self.get("/?source=tablet")

        self.assertEqual(handler.status, 200)
        self.assertIsNone(handler.error_status)
        page = handler.wfile.getvalue().decode("utf-8")
        self.assertIn("Daybook", page)
        self.assertIn("Goals", page)
        self.assertIn("Tasks", page)
        self.assertIn("Sessions", page)

    def test_dashboard_returns_local_records(self):
        conversations.save_conversation("chat-1", [{"role": "user", "content": "Plan the week"}])
        goals.add_goal("Build a steady routine")
        tasks.add_task("Book a checkup")
        memory.save_memory("I prefer morning appointments")

        handler = self.get("/api/dashboard")
        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))

        self.assertEqual(handler.status, 200)
        self.assertEqual(payload["conversations"][0]["label"], "Plan the week")
        self.assertEqual(payload["goals"][0]["title"], "Build a steady routine")
        self.assertEqual(payload["tasks"][0]["title"], "Book a checkup")
        self.assertEqual(payload["memories"][0]["content"], "I prefer morning appointments")

    def test_dashboard_actions_create_and_update_records(self):
        goal_response = self.post("/api/goals", {"title": "Learn to cook", "details": "One meal a week"})
        goal = json.loads(goal_response.wfile.getvalue().decode("utf-8"))["goal"]
        self.assertEqual(goal_response.status, 201)

        status_response = self.post(
            f"/api/goals/{goal['id']}/status",
            {"status": "completed"},
        )
        self.assertEqual(status_response.status, 200)
        self.assertEqual(goals.list_goals()[0]["status"], "completed")

        active_goal_id = goals.add_goal("Keep the kitchen tidy")
        task_response = self.post("/api/tasks", {
            "title": "Water the plants", "due_date": None, "goal_id": active_goal_id,
        })
        task = json.loads(task_response.wfile.getvalue().decode("utf-8"))["task"]
        self.assertEqual(task_response.status, 201)
        self.assertEqual(task["goal_id"], active_goal_id)
        update_response = self.post(f"/api/tasks/{task['id']}/update", {
            "goal_id": None,
            "clear_goal": True,
        })
        self.assertEqual(update_response.status, 200)
        self.assertIsNone(tasks.list_tasks()[0]["goal_id"])
        update_response = self.post(f"/api/tasks/{task['id']}/update", {
            "goal_id": active_goal_id,
        })
        self.assertEqual(update_response.status, 200)
        complete_response = self.post(f"/api/tasks/{task['id']}/complete", {})
        self.assertEqual(complete_response.status, 200)
        self.assertEqual(tasks.list_tasks(include_completed=True)[0]["status"], "completed")

        memory_response = self.post("/api/memories", {"content": "Keep the recipe simple"})
        saved = json.loads(memory_response.wfile.getvalue().decode("utf-8"))["memory"]
        self.assertEqual(memory_response.status, 201)
        delete_response = self.post(f"/api/memories/{saved['id']}/delete", {})
        self.assertEqual(delete_response.status, 200)
        self.assertEqual(memory.get_memories(), [])

        conversations.save_conversation("chat-meta", [
            {"role": "user", "content": "Plan the week"},
            {"role": "assistant", "content": "Let's start with your schedule."},
        ])
        metadata_response = self.post("/api/conversations/chat-meta/metadata", {
            "goal_id": active_goal_id,
            "needs_attention": True,
        })
        self.assertEqual(metadata_response.status, 200)
        summary = self.get("/api/conversations").wfile.getvalue().decode("utf-8")
        self.assertIn("Keep the kitchen tidy", summary)
        self.assertIn('"needs_attention": true', summary)

        recommendation_response = self.post("/api/recommendations", {
            "title": "Review the weekly plan",
            "rationale": "Several tasks share the same deadline.",
            "evidence": "Three tasks due Friday",
        })
        recommendation = json.loads(
            recommendation_response.wfile.getvalue().decode("utf-8")
        )["recommendation"]
        self.assertEqual(recommendation_response.status, 201)
        decision_response = self.post(
            f"/api/recommendations/{recommendation['id']}/decision",
            {"decision": "accepted"},
        )
        self.assertEqual(decision_response.status, 200)
        self.assertEqual(recommendations.list_recommendations()[0]["status"], "accepted")

    def test_ollama_status_route_reports_connection(self):
        with patch("src.agent.web.get_ollama_status", return_value={
            "connected": True,
            "model": "qwen3:1.7b",
            "model_available": True,
            "models": ["qwen3:1.7b"],
        }):
            handler = self.get("/api/ollama/status")

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(payload["model"], "qwen3:1.7b")
        self.assertTrue(payload["model_available"])

    def test_chat_saves_selected_goal_and_attention_state(self):
        goal_id = goals.add_goal("Make time to read")
        with patch("src.agent.web.OllamaAIProvider") as provider_class:
            provider = provider_class.return_value
            provider.conversation_id = "chat-linked"
            provider.generate_response.return_value = "Start with ten pages."
            handler = self.post("/api/chat", {
                "prompt": "Help me get started",
                "conversation_id": None,
                "goal_id": goal_id,
                "needs_attention": True,
            })

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        metadata = sessions.list_session_metadata()["chat-linked"]
        self.assertEqual(handler.status, 200)
        self.assertEqual(payload["goal_id"], goal_id)
        self.assertEqual(metadata["goal_id"], goal_id)
        self.assertEqual(metadata["needs_attention"], 1)

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
            [{
                "id": "chat-1",
                "label": "Help with my personal agent",
                "goal_id": None,
                "goal_title": None,
                "needs_attention": False,
            }],
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
        self.assertEqual(payload, {
            "id": "chat one",
            "history": history,
            "metadata": {"goal_id": None, "needs_attention": False},
        })

    def test_missing_conversation_returns_404(self):
        handler = self.get("/api/conversations/missing-chat")

        payload = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(handler.status, 404)
        self.assertEqual(payload, {"error": "Conversation not found"})


if __name__ == "__main__":
    unittest.main()
