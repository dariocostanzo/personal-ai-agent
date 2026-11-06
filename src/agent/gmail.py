"""Read-only Gmail search for explicit assistant requests."""
import base64
import os
from email.header import decode_header, make_header
from html.parser import HTMLParser
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DATA = Path(__file__).resolve().parents[2] / "data"
CLIENT = DATA / "gmail-credentials.json"
TOKEN = DATA / "gmail-token.json"
MAX_RESULTS = 5
MAX_BODY_CHARS = 3000


def _body(payload):
    plain, html = [], []
    def visit(part):
        encoded = part.get("body", {}).get("data")
        if encoded:
            data = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            text = data.decode("utf-8", errors="replace")
            if part.get("mimeType") == "text/plain":
                plain.append(text)
            elif part.get("mimeType") == "text/html":
                html.append(text)
        for child in part.get("parts", []):
            visit(child)
    visit(payload)
    if plain:
        return "\n".join(plain).strip()[:MAX_BODY_CHARS]
    if html:
        class Text(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []
                self.hidden = False
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style"):
                    self.hidden = True
            def handle_endtag(self, tag):
                if tag in ("script", "style"):
                    self.hidden = False
            def handle_data(self, data):
                if not self.hidden:
                    self.parts.append(data)
        parser = Text()
        parser.feed("\n".join(html))
        return " ".join(" ".join(parser.parts).split())[:MAX_BODY_CHARS]
    return ""


def _record(message):
    headers = {}
    for header in message.get("payload", {}).get("headers", []):
        name = header.get("name", "").lower()
        try:
            headers[name] = str(make_header(decode_header(header.get("value", ""))))
        except (LookupError, UnicodeError, ValueError):
            headers[name] = header.get("value", "")
    return {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", "(no subject)"),
        "date": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
        "body": _body(message.get("payload", {})),
    }


def authorize():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise RuntimeError("Install dependencies with pip install -r requirements.txt") from error
    if not CLIENT.exists():
        raise RuntimeError(f"Place Google Desktop OAuth credentials at {CLIENT}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(
        host="127.0.0.1", port=0, open_browser=False,
        authorization_prompt_message="Open this URL to grant read-only Gmail access:\n{url}",
        success_message="Gmail connected. You can close this tab.",
    )
    DATA.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(TOKEN, 0o600)


def _service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as error:
        raise RuntimeError("Install dependencies with pip install -r requirements.txt") from error
    if not TOKEN.exists():
        raise RuntimeError("Connect Gmail first: python -m src.agent.gmail authorize")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(TOKEN, 0o600)
    if not creds.valid:
        raise RuntimeError("Reconnect Gmail: python -m src.agent.gmail authorize")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def search_messages(query, max_results=MAX_RESULTS):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Gmail search query cannot be empty.")
    limit = max(1, min(int(max_results), MAX_RESULTS))
    api = _service().users().messages()
    result = api.list(userId="me", q=query.strip(), maxResults=limit).execute()
    return [_record(api.get(userId="me", id=m["id"], format="full").execute())
            for m in result.get("messages", [])[:limit]]


def prioritize_messages(messages):
    """Rank already-fetched mail using urgency cues and the local interest graph."""
    from src.agent import agent_state, goals, interests

    nodes = {
        item["topic"]: item["weight"]
        for item in interests.list_interests()["interests"]
    }
    active_goals = goals.list_goals(include_completed=False)
    ranked = []
    for message in messages:
        text = f"{message.get('subject', '')} {message.get('snippet', '')} {message.get('body', '')}"
        lower = text.casefold()
        topics = interests.classify_topics(text)
        urgency = sum(term in lower for term in (
            "urgent", "action required", "deadline", "due today", "asap",
        ))
        relevance = sum(nodes.get(topic, 0.5) for topic in topics) / len(topics)
        score = urgency * 0.2 + relevance * 0.5
        matching_goals = [
            goal["title"] for goal in active_goals
            if any(word in (goal["title"] + " " + goal["details"]).casefold()
                   for word in lower.split() if len(word) > 4)
        ][:3]
        item = dict(message)
        item.update({
            "priority": "high" if score >= 0.75 else "normal",
            "priority_score": round(score, 3),
            "topics": topics,
            "matching_goals": matching_goals,
        })
        ranked.append(item)
        if item.get("id"):
            interests.record_action(
                "email_interaction", text, "email", item["id"],
                "Email appeared in an explicitly requested Gmail search.",
            )
        agent_state.add_decision(
            "email_triage", item.get("subject", "(no subject)"),
            "Ranked from urgency language and local interest weights.",
            {"priority": item["priority"], "topics": topics,
             "matching_goals": matching_goals},
        )
    return sorted(ranked, key=lambda item: (-item["priority_score"], item.get("date", "")))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Read-only Gmail connector")
    parser.add_argument("action", choices=("authorize", "search"))
    parser.add_argument("query", nargs="?")
    args = parser.parse_args()
    if args.action == "authorize":
        authorize()
    elif not args.query:
        parser.error("search requires a Gmail query")
    else:
        for m in search_messages(args.query):
            print(f"From: {m['from']}\nSubject: {m['subject']}\n"
                  f"Date: {m['date']}\n\n{m['body'] or m['snippet']}\n")


if __name__ == "__main__":
    main()
