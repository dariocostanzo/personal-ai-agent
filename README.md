# Personal AI Agent

A locally running Python personal AI agent. The current version provides persistent memory, chat sessions and conversation management. It uses a mock AI provider for testing.

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

## Architecture

```text
personal-agent/
│
├── src/
│   └── agent/
│       ├── main.py           # Application entry point and menu
│       ├── ai.py             # AI provider interface and mock provider
│       ├── memory.py         # Persistent memory management
│       ├── conversations.py  # Conversation storage and retrieval
│       ├── config.py         # Environment configuration
│       └── logger.py         # Application logging
│
├── data/
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
- **ai.py** defines the AI provider interface. The current mock provider generates test responses.
- **memory.py** stores and manages persistent memories in SQLite.
- **conversations.py** stores separate chat histories in JSON, identified by unique IDs.
- **config.py** loads environment variables from `.env`.
- **logger.py** handles application logging.

## Data and privacy

Personal memories and conversations are stored locally in the `data/` directory.

The `.env` file may contain secrets and must never be committed to Git. Personal databases and conversation histories should also remain outside the repository.

## Current status

This is an early development version. The next planned stage is integrating a real AI provider while keeping the memory and conversation systems independent of the provider.
