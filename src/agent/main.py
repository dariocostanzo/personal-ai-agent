from src.agent.logger import logger
from src.agent.memory import (
    save_memory,
    get_memories,
    search_memories,
    update_memory,
    delete_memory,
)


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
