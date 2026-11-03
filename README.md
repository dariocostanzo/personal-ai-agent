# Personal AI Agent

A locally running Python personal AI agent using Ollama, SQLite memory and saved conversations. Browser chat also supports read-only Gmail search after OAuth setup and local task management.

## Requirements

- Ubuntu or another Linux distribution
- Python 3
- `venv` support

## Installation

From the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the agent

Every time you want to start the agent:

```bash
cd ~/projects/personal-agent
source .venv/bin/activate
python -m src.agent.main
```

When finished, select `0` to exit the agent, then run:

```bash
deactivate
```

## Local web hub

Start the browser dashboard from the project directory with the virtual environment active:

```bash
python -m src.agent.web
```

Open <http://localhost:8000>. The server binds to localhost and brings sessions, tasks, memories, goals, a due-date calendar, and recommendation decisions together. Sessions and tasks can be linked to active goals; sessions can be marked as needing attention. The Ollama badge reports whether the configured model is available.

Recommendation decisions are recorded only. Accepting one does not perform an external action. The calendar displays task due dates but does not send background notifications.

Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env` to use a different local Ollama endpoint or model. The defaults are `http://localhost:11434` and `qwen3:1.7b`.

## Features

The current menu provides:

1. Save memory
2. Show all memories
3. Search memories
4. Update memory
5. Delete memory
6. Chat with AI
7. List conversations
8. Delete conversation

Chat task commands:

- Add task: call dentist
- Add task: pay rent | due 2026-11-05 (due dates use YYYY-MM-DD)
- Remind me to buy milk
- List my tasks
- What should I do today? (shows overdue, due today, and next 7 days)
- Find tasks for rent
- Rename task #1 to pay the water bill
- Reschedule task #1 to 2026-11-12
- Clear due date for task #1
- Complete task #1
- What are my goals? (lists active goals and their linked open tasks)

Chat memory commands:

- Remember that I prefer decaf coffee
- Find memories for coffee
- What do you remember about coffee?

Memory commands only save or search when the request matches these explicit patterns. Use the existing menu to update or delete a memory.

Document search:

- Put `.txt`, `.md`, `.csv`, `.json`, or `.rst` files in `data/documents`.
- Ask: Find documents about the fridge warranty
- Search is local and read-only. It skips hidden files, unsupported formats, and files larger than 1 MB. Set the `AGENT_DOCUMENTS_DIR` environment variable before starting the app to use a different folder.

Tasks are stored in data/tasks.db. Completing a task keeps it in task history. This version tracks due dates but does not send background notifications.

## Architecture

```text
personal-agent/
│
├── src/
│   └── agent/
│       ├── main.py           # Application entry point and menu
│       ├── ai.py             # Ollama chat and explicit tool routing
│       ├── dashboard.html    # Local browser hub
│       ├── memory.py         # Persistent memory management
│       ├── goals.py          # Personal goal tracking
│       ├── sessions.py       # Goal and attention metadata for sessions
│       ├── recommendations.py # Recommendation decision ledger
│       ├── tasks.py          # Local task tracking
│       ├── gmail.py          # Read-only Gmail search
│       ├── web.py            # Browser chat server
│       ├── conversations.py  # Conversation storage and retrieval
│       ├── config.py         # Environment configuration
│       └── logger.py         # Application logging
│
├── data/
│   ├── tasks.db              # Local task list
│   ├── goals.db              # Personal goals
│   ├── sessions.db           # Session metadata
│   ├── recommendations.db    # Recommendation decisions
│   ├── memory.db             # SQLite memory database
│   ├── conversations.json   # Saved chat histories
│   └── .gitkeep
│
├── logs/
│   └── agent.log             # Application logs
│
├── tests/                    # Automated tests
├── requirements.txt          # Python dependencies
├── .env.example              # Example environment configuration
└── README.md
```

## How it works

- **main.py** runs the application and handles user interaction.
- **ai.py** sends general chat to local Ollama and routes explicit task and Gmail requests to limited local tools. Task actions use fixed command patterns; general chat does not execute them.
- **memory.py** stores and manages persistent memories in SQLite.
- **conversations.py** stores separate chat histories in JSON, identified by unique IDs.
- **tasks.py** stores tasks in a separate local SQLite database. Completed tasks stay in history.
- **sessions.py** stores goal links and manually set attention flags separately from chat histories.
- **goals.py** stores personal goals and their active or completed status in SQLite.
- **recommendations.py** stores manually entered suggestions and accepted or declined decisions; decisions do not execute actions.
- **web.py** serves the local dashboard and its JSON endpoints; **dashboard.html** provides the browser interface.
- **documents.py** searches only supported small text files in the configured documents folder.
- **config.py** loads environment variables from `.env`.
- **logger.py** handles application logging.

## Data and privacy

Memories, conversations, tasks, goals, session metadata, recommendations and Gmail OAuth files are stored locally in the project data directory, which is excluded from Git.

The `.env` file may contain secrets and must never be committed to Git. Personal databases and conversation histories should also remain outside the repository.

## Current status

- General chat uses local Ollama.
- The local browser hub includes sessions, tasks, memories, goals, a due-date calendar, and recommendation review.
- Goal questions in chat use local goal and task records; general chat receives active goal and linked-task context.
- Tasks can be linked or reassigned to active goals; sessions can be grouped by goal and manually flagged as needing attention.
- The calendar shows dated tasks by month; reminders do not run in the background.
- Recommendations are entered for review, then marked accepted or declined without performing the suggested action.
- The dashboard shows Ollama connectivity and whether its configured model is installed.
- Explicit chat commands can add, list and complete tasks locally.
- Task commands can search, rename, reschedule, clear due dates, and summarize overdue, due-today, and upcoming work.
- Explicit chat commands can save and search memories without calling Ollama; updating and deleting memories remains available in the menu.
- Explicit document searches return matching local file snippets without calling Ollama.
- Gmail search is read-only and requires the OAuth setup in GMAIL_SETUP.md.
- Task due dates are saved, but background notifications are not implemented.
- The browser server binds to localhost; remote access is intended to go through Tailscale.
