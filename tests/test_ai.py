import json
import unittest
from unittest.mock import patch

from src.agent import ai


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestGoalAwareChat(unittest.TestCase):
    def test_goal_question_uses_local_data_without_ollama(self):
        goal = {"id": 4, "title": "Build a routine", "details": "Walk every day"}
        task = {"id": 2, "title": "Walk after lunch", "goal_id": 4}
        with patch("src.agent.ai.list_goals", return_value=[goal]), \
             patch("src.agent.ai.list_tasks", return_value=[task]), \
             patch("src.agent.ai.get_conversation", return_value=[]), \
             patch("src.agent.ai.save_conversation") as save, \
             patch("src.agent.ai.urllib.request.urlopen") as ollama:
            provider = ai.OllamaAIProvider()
            answer = provider.generate_response("What are my goals?")

        self.assertIn("Build a routine", answer)
        self.assertIn("Walk after lunch", answer)
        ollama.assert_not_called()
        save.assert_called_once()

    def test_general_chat_includes_goals_and_session_goal_context(self):
        with patch("src.agent.ai.get_conversation", return_value=[]), \
             patch("src.agent.ai.save_conversation"), \
             patch("src.agent.ai.get_memories", return_value=[]), \
             patch("src.agent.ai.list_goals", return_value=[{
                 "id": 4, "title": "Build a routine", "details": "Walk every day"
             }]), \
             patch("src.agent.ai.list_tasks", return_value=[{
                 "title": "Walk after lunch", "goal_id": 4
             }]), \
             patch("src.agent.ai.list_session_metadata", return_value={
                 "chat-1": {"goal_id": 4}
             }), \
             patch("src.agent.ai.urllib.request.urlopen", return_value=FakeResponse({
                 "message": {"content": "Try a short walk after lunch."}
             })) as ollama:
            provider = ai.OllamaAIProvider("chat-1")
            provider.generate_response("How should I make progress?")

        payload = json.loads(ollama.call_args.args[0].data.decode("utf-8"))
        system_message = payload["messages"][0]["content"]
        self.assertIn("Build a routine", system_message)
        self.assertIn("Walk after lunch", system_message)
        self.assertIn("current session goal", system_message)

    def test_ollama_status_reports_model_availability(self):
        with patch("src.agent.ai.urllib.request.urlopen", return_value=FakeResponse({
            "models": [{"name": ai.OLLAMA_MODEL}]
        })):
            status = ai.get_ollama_status()

        self.assertTrue(status["connected"])
        self.assertTrue(status["model_available"])


if __name__ == "__main__":
    unittest.main()