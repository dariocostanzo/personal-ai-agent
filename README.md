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
- Complete task #1

Tasks are stored in data/tasks.db. Completing a task keeps it in task history. This version tracks due dates but does not send background notifications.

## Architecture

```text
personal-agent/
│
├── src/
│   └── agent/
│       ├── main.py           # Application entry point and menu
│       ├── ai.py             # Ollama chat and explicit tool routing
│       ├── memory.py         # Persistent memory management
│       ├── tasks.py          # Local task tracking
│       ├── gmail.py          # Read-only Gmail search
│       ├── web.py            # Browser chat server
│       ├── conversations.py  # Conversation storage and retrieval
│       ├── config.py         # Environment configuration
│       └── logger.py         # Application logging
│
├── data/
│   ├── tasks.db              # Local task list
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
- **ai.py** sends general chat to local Ollama and routes explicit task and Gmail requests to limited local tools.
- **memory.py** stores and manages persistent memories in SQLite.
- **conversations.py** stores separate chat histories in JSON, identified by unique IDs.
- **tasks.py** stores tasks in a separate local SQLite database. Completed tasks stay in history.
- **config.py** loads environment variables from `.env`.
- **logger.py** handles application logging.

## Data and privacy

Memories, conversations, tasks and Gmail OAuth files are stored locally in the project data directory, which is excluded from Git.

The `.env` file may contain secrets and must never be committed to Git. Personal databases and conversation histories should also remain outside the repository.

## Current status

- General chat uses local Ollama.
- Explicit chat commands can add, list and complete tasks locally.
- Gmail search is read-only and requires the OAuth setup in GMAIL_SETUP.md.
- Task due dates are saved, but background notifications are not implemented.
- The browser server binds to localhost; remote access is intended to go through Tailscale.
