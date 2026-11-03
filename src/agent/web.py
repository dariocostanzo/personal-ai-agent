import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from src.agent import conversations, goals, memory, tasks

from src.agent.ai import OllamaAIProvider

HTML = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")


def _conversation_summaries():
    summaries = []
    for conversation_id, history in conversations.load_conversations().items():
        last_prompt = next(
            (
                message.get("content", "")
                for message in reversed(history)
                if message.get("role") == "user"
            ),
            "",
        )
        label = " ".join(last_prompt.split())[:60] or conversation_id
        summaries.append({"id": conversation_id, "label": label})
    return summaries


def _read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 100000:
        raise ValueError("Invalid request size")
    data = json.loads(handler.rfile.read(length))
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    return data


class ChatHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_path = urlsplit(self.path)
        path = parsed_path.path

        if path == "/api/dashboard":
            self.send_json({
                "conversations": _conversation_summaries(),
                "task_overview": tasks.task_overview(),
                "tasks": tasks.list_tasks(include_completed=True),
                "goals": goals.list_goals(),
                "memories": [dict(zip(("id", "content", "created_at"), row))
                             for row in memory.get_memories()],
            })
            return

        if path == "/api/tasks":
            self.send_json({"tasks": tasks.list_tasks(include_completed=True)})
            return

        if path == "/api/goals":
            self.send_json({"goals": goals.list_goals()})
            return

        if path == "/api/memories":
            query = parse_qs(parsed_path.query).get("q", [""])[0].strip()
            records = memory.search_memories(query) if query else memory.get_memories()
            self.send_json({"memories": [dict(zip(
                ("id", "content", "created_at"), row
            )) for row in records]})
            return

        if path == "/api/conversations":
            self.send_json({"conversations": _conversation_summaries()})
            return

        conversation_prefix = "/api/conversations/"
        if path.startswith(conversation_prefix):
            encoded_id = path[len(conversation_prefix):]
            if not encoded_id or "/" in encoded_id:
                self.send_json({"error": "Not found"}, 404)
                return

            conversation_id = unquote(encoded_id)
            history = conversations.get_conversation(conversation_id)
            if not history:
                self.send_json({"error": "Conversation not found"}, 404)
                return

            self.send_json({"id": conversation_id, "history": history})
            return

        if path != "/":
            self.send_error(404)
            return

        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/chat", "/api/goals", "/api/tasks", "/api/memories") and not (
            path.startswith("/api/goals/")
            or path.startswith("/api/tasks/")
            or path.startswith("/api/memories/")
        ):
            self.send_json({"error": "Not found"}, 404)
            return

        if path != "/api/chat":
            try:
                data = _read_json_body(self)
                if path == "/api/goals":
                    goal_id = goals.add_goal(data.get("title"), data.get("details", ""))
                    goal = next(goal for goal in goals.list_goals() if goal["id"] == goal_id)
                    self.send_json({"goal": goal}, 201)
                    return

                if path.startswith("/api/goals/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "status":
                        self.send_json({"error": "Not found"}, 404)
                        return
                    updated = goals.set_goal_status(int(parts[2]), data.get("status"))
                    if not updated:
                        self.send_json({"error": "Goal not found"}, 404)
                        return
                    self.send_json({"ok": True})
                    return

                if path == "/api/tasks":
                    task_id = tasks.add_task(data.get("title"), data.get("due_date"))
                    task = next(task for task in tasks.list_tasks(True) if task["id"] == task_id)
                    self.send_json({"task": task}, 201)
                    return

                if path.startswith("/api/tasks/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "complete":
                        self.send_json({"error": "Not found"}, 404)
                        return
                    if not tasks.complete_task(int(parts[2])):
                        self.send_json({"error": "Open task not found"}, 404)
                        return
                    self.send_json({"ok": True})
                    return

                if path == "/api/memories":
                    content = data.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("Memory cannot be empty.")
                    memory_id = memory.save_memory(content.strip())
                    record = next(row for row in memory.get_memories() if row[0] == memory_id)
                    self.send_json({"memory": dict(zip(
                        ("id", "content", "created_at"), record
                    ))}, 201)
                    return

                if path.startswith("/api/memories/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "delete":
                        self.send_json({"error": "Not found"}, 404)
                        return
                    if not memory.delete_memory(int(parts[2])):
                        self.send_json({"error": "Memory not found"}, 404)
                        return
                    self.send_json({"ok": True})
                    return
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                self.send_json({"error": str(error)}, 400)
                return
            except Exception as error:
                self.send_json({"error": str(error)}, 500)
                return

        try:
            data = _read_json_body(self)
            prompt = data.get("prompt", "").strip()
            conversation_id = data.get("conversation_id") or None

            if not prompt:
                self.send_json({"error": "Message cannot be empty"}, 400)
                return

            ai = OllamaAIProvider(conversation_id)
            answer = ai.generate_response(prompt)

            self.send_json({
                "response": answer,
                "conversation_id": ai.conversation_id
            })

        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, format, *args):
        print(f"[WEB] {args[0]}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ChatHandler)
    print("Personal AI Assistant running at http://localhost:8000")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
