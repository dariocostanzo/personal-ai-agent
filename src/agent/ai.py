import uuid

from src.agent.conversations import (
    save_conversation,
    get_conversation,
)


class AIProvider:
    def generate_response(self, prompt):
        raise NotImplementedError


class MockAIProvider(AIProvider):
    """Temporary provider for testing without API costs."""

    def __init__(self, conversation_id=None):
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.conversation_history = get_conversation(self.conversation_id)

    def generate_response(self, prompt):
        self.conversation_history.append({
            "role": "user",
            "content": prompt
        })

        response = f"Test AI response received: {prompt}"

        self.conversation_history.append({
            "role": "assistant",
            "content": response
        })

        save_conversation(
            self.conversation_id,
            self.conversation_history
        )

        return response
