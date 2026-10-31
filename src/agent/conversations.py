import json
from pathlib import Path

CONVERSATIONS_FILE = Path("data/conversations.json")


def load_conversations():
    if not CONVERSATIONS_FILE.exists():
        return {}

    with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Preserve conversations created by the previous storage format.
    if isinstance(data, list):
        return {"legacy": data}

    return data


def save_conversation(conversation_id, history):
    conversations = load_conversations()
    conversations[conversation_id] = history

    CONVERSATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(conversations, file, indent=4)


def get_conversation(conversation_id):
    conversations = load_conversations()
    return conversations.get(conversation_id, [])


def list_conversations():
    conversations = load_conversations()
    return list(conversations.keys())


def delete_conversation(conversation_id):
    conversations = load_conversations()

    if conversation_id not in conversations:
        return False

    del conversations[conversation_id]

    CONVERSATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(conversations, file, indent=4)

    return True
