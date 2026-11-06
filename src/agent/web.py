import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from src.agent import (
    agent_state,
    calendar,
    conversations,
    goals,
    guardians,
    interests,
    memory,
    news,
    proposals,
    recommendations,
    sessions,
    tasks,
)

from src.agent.ai import OllamaAIProvider, get_ollama_status
from src.agent.providers import status as provider_status

HTML = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")


def _conversation_summaries():
    summaries = []
    metadata_by_id = sessions.list_session_metadata()
    goals_by_id = {goal["id"]: goal for goal in goals.list_goals()}
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
        metadata = metadata_by_id.get(conversation_id, {})
        goal = goals_by_id.get(metadata.get("goal_id"))
        summaries.append({
            "id": conversation_id,
            "label": label,
            "goal_id": metadata.get("goal_id"),
            "goal_title": goal["title"] if goal else None,
            "needs_attention": bool(metadata.get("needs_attention", 0)),
        })
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
                "recommendations": recommendations.list_recommendations(),
                "memories": [dict(zip(("id", "content", "created_at"), row))
                             for row in memory.get_memories()],
                "news": news.list_items(),
                "news_sources": news.list_sources(),
                "news_run": news.latest_run(),
                "interests": interests.list_interests(),
                "guardians": agent_state.latest_guardian_checks(),
                "proposals": proposals.list_proposals(),
                "decisions": agent_state.list_decisions(),
                "model_usage": agent_state.usage_summary(),
                "provider": provider_status(),
                "calendar": calendar.list_events(),
            })
            return

        if path == "/api/news":
            topic = parse_qs(parsed_path.query).get("topic", [""])[0].strip() or None
            self.send_json({
                "items": news.list_items(topic=topic),
                "sources": news.list_sources(),
                "last_run": news.latest_run(),
            })
            return

        if path == "/api/interests":
            self.send_json(interests.list_interests())
            return

        if path == "/api/guardians":
            checks = agent_state.latest_guardian_checks()
            self.send_json({
                "checks": checks,
                "needs_attention": any(
                    item["status"] == "attention" for item in checks
                ),
            })
            return

        if path == "/api/proposals":
            self.send_json({"proposals": proposals.list_proposals()})
            return

        if path == "/api/decisions":
            self.send_json({"decisions": agent_state.list_decisions()})
            return

        if path == "/api/model/usage":
            self.send_json({
                "usage": agent_state.usage_summary(),
                "provider": provider_status(),
            })
            return

        if path == "/api/calendar":
            self.send_json({"events": calendar.list_events()})
            return

        if path == "/api/tasks":
            self.send_json({"tasks": tasks.list_tasks(include_completed=True)})
            return

        if path == "/api/ollama/status":
            self.send_json(get_ollama_status())
            return

        if path == "/api/recommendations":
            self.send_json({"recommendations": recommendations.list_recommendations()})
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

            self.send_json({
                "id": conversation_id,
                "history": history,
                "metadata": sessions.list_session_metadata().get(
                    conversation_id,
                    {"goal_id": None, "needs_attention": False},
                ),
            })
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
        if path not in (
            "/api/chat", "/api/goals", "/api/tasks", "/api/memories",
            "/api/recommendations", "/api/news/sources", "/api/news/refresh",
            "/api/proposals", "/api/proposals/suggest", "/api/guardians",
        ) and not (
            path.startswith("/api/goals/")
            or path.startswith("/api/tasks/")
            or path.startswith("/api/memories/")
            or path.startswith("/api/recommendations/")
            or path.startswith("/api/conversations/")
            or path.startswith("/api/news/")
            or path.startswith("/api/interests/")
            or path.startswith("/api/proposals/")
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
                    task_id = tasks.add_task(
                        data.get("title"), data.get("due_date"), data.get("goal_id") or None
                    )
                    task = next(task for task in tasks.list_tasks(True) if task["id"] == task_id)
                    self.send_json({"task": task}, 201)
                    return

                if path.startswith("/api/tasks/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4:
                        self.send_json({"error": "Not found"}, 404)
                        return
                    if parts[3] == "update":
                        changed = tasks.update_task(
                            int(parts[2]),
                            goal_id=data.get("goal_id") or None,
                            clear_goal=bool(data.get("clear_goal", False)),
                        )
                        if not changed:
                            self.send_json({"error": "Open task not found"}, 404)
                            return
                        self.send_json({"ok": True})
                        return
                    if parts[3] == "ignore":
                        if not tasks.ignore_task(int(parts[2])):
                            self.send_json({"error": "Open task not found"}, 404)
                            return
                        self.send_json({"ok": True})
                        return
                    if parts[3] != "complete":
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

                if path == "/api/recommendations":
                    recommendation_id = recommendations.add_recommendation(
                        data.get("title"), data.get("rationale", ""), data.get("evidence", "")
                    )
                    item = next(
                        item for item in recommendations.list_recommendations()
                        if item["id"] == recommendation_id
                    )
                    self.send_json({"recommendation": item}, 201)
                    return

                if path.startswith("/api/recommendations/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "decision":
                        self.send_json({"error": "Not found"}, 404)
                        return
                    if not recommendations.decide_recommendation(
                        int(parts[2]), data.get("decision")
                    ):
                        self.send_json({"error": "Pending recommendation not found"}, 404)
                        return
                    self.send_json({"ok": True})
                    return

                if path == "/api/news/sources":
                    source_id = news.add_source(
                        data.get("name"), data.get("kind"), data.get("location")
                    )
                    source = next(item for item in news.list_sources()
                                  if item["id"] == source_id)
                    self.send_json({"source": source}, 201)
                    return

                if path == "/api/news/refresh":
                    result = news.run_digest(full=bool(data.get("full", False)))
                    self.send_json(result, 202)
                    return

                if path.startswith("/api/news/"):
                    parts = path.strip("/").split("/")
                    if len(parts) == 4 and parts[2] == "sources" and parts[3].isdigit():
                        if not news.set_source_enabled(
                            int(parts[3]), data.get("enabled")
                        ):
                            self.send_json({"error": "News source not found"}, 404)
                            return
                        self.send_json({"ok": True})
                        return
                    if len(parts) == 4 and parts[3] == "feedback":
                        if not news.feedback(int(parts[2]), data.get("action")):
                            self.send_json({"error": "News item not found"}, 404)
                            return
                        self.send_json({"ok": True})
                        return
                    self.send_json({"error": "Not found"}, 404)
                    return

                if path.startswith("/api/interests/"):
                    topic = unquote(path[len("/api/interests/"):])
                    interests.set_interest(topic, data.get("weight"))
                    self.send_json({"ok": True})
                    return

                if path == "/api/proposals":
                    proposal_id = proposals.propose(
                        data.get("kind"), data.get("title"),
                        data.get("details", ""), data.get("payload", {}),
                    )
                    proposal = next(item for item in proposals.list_proposals()
                                    if item["id"] == proposal_id)
                    self.send_json({"proposal": proposal}, 201)
                    return

                if path == "/api/proposals/suggest":
                    suggested = proposals.suggest()
                    self.send_json({"proposals": suggested}, 201)
                    return

                if path.startswith("/api/proposals/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] != "review":
                        self.send_json({"error": "Not found"}, 404)
                        return
                    if not proposals.review(
                        int(parts[2]), data.get("decision"),
                        data.get("title"), data.get("details"), data.get("payload"),
                    ):
                        self.send_json({"error": "Pending proposal not found"}, 404)
                        return
                    self.send_json({"ok": True})
                    return

                if path == "/api/guardians":
                    guardians.add_service(data.get("name"), data.get("url"))
                    self.send_json({"ok": True}, 201)
                    return

                if path.startswith("/api/conversations/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[3] not in ("metadata", "attention"):
                        self.send_json({"error": "Not found"}, 404)
                        return
                    conversation_id = unquote(parts[2])
                    if not conversations.get_conversation(conversation_id):
                        self.send_json({"error": "Conversation not found"}, 404)
                        return
                    if parts[3] == "metadata":
                        if "goal_id" in data:
                            sessions.set_session_goal(conversation_id, data["goal_id"] or None)
                        if "needs_attention" in data:
                            sessions.set_needs_attention(conversation_id, data["needs_attention"])
                    else:
                        sessions.set_needs_attention(
                            conversation_id, data.get("needs_attention")
                        )
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
            if "goal_id" in data:
                sessions.set_session_goal(ai.conversation_id, data["goal_id"] or None)
            if "needs_attention" in data:
                sessions.set_needs_attention(ai.conversation_id, data["needs_attention"])
            answer = ai.generate_response(prompt)

            self.send_json({
                "response": answer,
                "conversation_id": ai.conversation_id,
                "goal_id": data.get("goal_id"),
            })

        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, format, *args):
        print(f"[WEB] {args[0]}")


if __name__ == "__main__":
    from src.agent.jobs import start_background_jobs

    start_background_jobs()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ChatHandler)
    print("Personal AI Assistant running at http://localhost:8000")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
