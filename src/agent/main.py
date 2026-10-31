from src.agent.logger import logger
from src.agent.memory import (
    save_memory,
    get_memories,
    search_memories,
    update_memory,
    delete_memory,
)
from src.agent.ai import MockAIProvider
from src.agent.conversations import list_conversations, delete_conversation

def get_memory_id():
    try:
        return int(input("Memory ID: ").strip())
    except ValueError:
        print("Please enter a valid number.")
        return None


def main():
    logger.info("Personal AI Agent started.")

    while True:
        print("\n--- PERSONAL AI AGENT ---")
        print("1. Save memory")
        print("2. Show all memories")
        print("3. Search memories")
        print("4. Update memory")
        print("5. Delete memory")
        print("6. Chat with AI")
        print("7. List conversations")
        print("8. Delete conversation")
        print("0. Exit")

        choice = input("\nChoose an option: ").strip()

        try:
            if choice == "1":
                content = input("What should I remember? ").strip()
                if content:
                    print(f"Saved memory #{save_memory(content)}")
                else:
                    print("Memory cannot be empty.")

            elif choice == "2":
                memories = get_memories()
                for memory in memories:
                    print(memory)
                if not memories:
                    print("No memories found.")

            elif choice == "3":
                query = input("Search for: ").strip()
                for memory in search_memories(query):
                    print(memory)

            elif choice == "4":
                memory_id = get_memory_id()
                if memory_id is not None:
                    content = input("New content: ").strip()
                    if content:
                        print("Updated." if update_memory(memory_id, content) else "Not found.")
                    else:
                        print("Memory cannot be empty.")

            elif choice == "5":
                memory_id = get_memory_id()
                if memory_id is not None:
                    print("Deleted." if delete_memory(memory_id) else "Not found.")

            elif choice == "6":
                conversations = list_conversations()

                print("\n--- AI CHAT ---")

                if conversations:
                    print("Existing conversations:")
                    for conversation_id in conversations:
                        print(conversation_id)

                conversation_id = input(
                    "\nConversation ID (Enter for new conversation): "
                ).strip()

                ai = MockAIProvider(conversation_id or None)

                print(f"Active conversation: {ai.conversation_id}")
                print("Type 'exit' to return to the main menu.")

                while True:
                    prompt = input("\nYou: ").strip()

                    if prompt.lower() == "exit":
                        break

                    if prompt:
                        response = ai.generate_response(prompt)
                        print(f"AI: {response}")
                    else:
                        print("Message cannot be empty.")

            elif choice == "7":
                conversations = list_conversations()

                if conversations:
                    print("\n--- SAVED CONVERSATIONS ---")
                    for conversation_id in conversations:
                        print(conversation_id)
                else:
                    print("No conversations found.")

            elif choice == "8":
                conversations = list_conversations()

                if conversations:
                    print("\n--- SAVED CONVERSATIONS ---")
                    for conversation_id in conversations:
                        print(conversation_id)

                    conversation_id = input(
                        "\nConversation ID to delete: "
                    ).strip()

                    confirm = input(
                        f"Delete conversation {conversation_id}? (yes/no): "
                    ).strip().lower()

                    if confirm == "yes":
                        if delete_conversation(conversation_id):
                            print("Conversation deleted.")
                        else:
                            print("Conversation not found.")
                    else:
                        print("Deletion cancelled.")
                else:
                    print("No conversations found.")


            elif choice == "0":
                print("Goodbye.")
                break

            else:
                print("Invalid option.")

        except Exception:
            logger.exception("An unexpected error occurred.")
            print("Something went wrong. Check logs/agent.log.")


if __name__ == "__main__":
    main()
