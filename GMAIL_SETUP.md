# Gmail setup (read-only)

Gmail searches run only when explicitly requested. The integration cannot send,
delete, archive, or modify mail. Each search returns at most five messages and
each body is limited to 3,000 characters. Fetched mail is sent to local Ollama.

1. In Google Cloud Console, create or select a project and enable Gmail API.
2. Configure the OAuth consent screen. For a personal Gmail account, choose External and add your own Google account as a test user.
3. Create an OAuth client ID with application type Desktop app and download its JSON.
4. In WSL save the file as ~/projects/personal-agent/data/gmail-credentials.json.
5. From the project directory activate .venv and run:
   python -m pip install -r requirements.txt
   python -m src.agent.gmail authorize
6. Follow the printed URL and grant read-only Gmail access. The refresh token is
   saved in data/gmail-token.json. The data directory is excluded from Git.

Google may show an unverified-app warning. Proceed only if you created the
Google Cloud project and OAuth client yourself.

Chat examples:
- Search my Gmail for from:alice@example.com newer_than:30d
- Search my Gmail for subject:invoice
- Check my unread emails
- Check my inbox
