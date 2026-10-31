import json
import uuid
import urllib.request
import urllib.error

from src.agent.conversations import save_conversation, get_conversation
from src.agent.memory import get_memories


class AIProvider:
    def generate_response(self, prompt):
        raise NotImplementedError


class OllamaAIProvider(AIProvider):
    def __init__(self, conversation_id=None):
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.conversation_history = get_conversation(self.conversation_id)
        self.model = "qwen3:1.7b"
        self.api_url = "http://localhost:11434/api/chat"

    def generate_response(self, prompt):
        self.conversation_history.append({
            "role": "user",
            "content": prompt
        })

        memories = get_memories()
        memory_context = "\n".join(
            f"- {memory[1]}" for memory in memories[-30:]
        )

        system_message = (
            "You are a personal AI assistant. "
            "Use the saved memories below when relevant. "
            "Treat them as facts supplied by the user. "
            "Do not invent memories or claim to know information "
            "that is not present. If a memory is irrelevant, ignore it.\n\n"
            "SAVED USER MEMORIES:\n"
            + (memory_context if memory_context else "No saved memories yet.")
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                *self.conversation_history[-20:]
            ],
            "stream": False,
            "think": False
        }

        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))

            answer = result["message"]["content"]

        except (urllib.error.URLError, TimeoutError) as error:
            self.conversation_history.pop()
            raise RuntimeError(f"Could not connect to Ollama: {error}")

        self.conversation_history.append({
            "role": "assistant",
            "content": answer
        })

        save_conversation(
            self.conversation_id,
            self.conversation_history
        )

        return answer
