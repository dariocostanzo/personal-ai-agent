import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.agent.ai import OllamaAIProvider

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Personal AI Assistant</title>
<style>
* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f4f5f7;
    color: #202124;
}
header {
    background: #202124;
    color: white;
    padding: 18px 22px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
h1 { font-size: 19px; margin: 0; }
button {
    border: 0;
    border-radius: 7px;
    padding: 11px 16px;
    cursor: pointer;
    background: #202124;
    color: white;
}
header button { background: #444; }
main {
    max-width: 850px;
    margin: 25px auto;
    padding: 0 15px;
}
#messages {
    background: white;
    border-radius: 10px;
    min-height: 60vh;
    padding: 20px;
    box-shadow: 0 2px 8px #0000000c;
}
.message {
    white-space: pre-wrap;
    line-height: 1.55;
    margin: 12px 0 20px;
    padding: 13px 15px;
    border-radius: 9px;
    max-width: 90%;
}
.user { background: #e8eefc; margin-left: auto; }
.assistant { background: #f0f1f3; margin-right: auto; }
#status { color: #666; font-size: 13px; margin: 12px 3px; }
form { display: flex; gap: 10px; margin-top: 15px; }
textarea {
    flex: 1;
    resize: vertical;
    min-height: 52px;
    max-height: 180px;
    padding: 14px;
    border: 1px solid #ccc;
    border-radius: 8px;
    font: inherit;
}
form button { min-width: 85px; }
@media (max-width: 600px) {
    main { margin: 12px auto; }
    #messages { min-height: 65vh; padding: 13px; }
    .message { max-width: 100%; }
}
</style>
</head>
<body>
<header>
    <h1>Personal AI Assistant</h1>
    <button id="newChat">New chat</button>
</header>
<main>
    <div id="messages">
        <div class="message assistant">Hello. I'm your personal AI assistant. How can I help?</div>
    </div>
    <div id="status">Connected to your local assistant</div>
    <form id="chatForm">
        <textarea id="prompt" placeholder="Type your message..." required></textarea>
        <button id="send" type="submit">Send</button>
    </form>
</main>
<script>
let conversationId = null;
const messages = document.getElementById("messages");
const promptBox = document.getElementById("prompt");
const statusBox = document.getElementById("status");
const sendButton = document.getElementById("send");

function addMessage(text, role) {
    const div = document.createElement("div");
    div.className = "message " + role;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

document.getElementById("newChat").addEventListener("click", () => {
    conversationId = null;
    messages.innerHTML = "";
    addMessage("New conversation started. What would you like to discuss?", "assistant");
    statusBox.textContent = "New conversation";
    promptBox.focus();
});

document.getElementById("chatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const prompt = promptBox.value.trim();
    if (!prompt) return;

    addMessage(prompt, "user");
    promptBox.value = "";
    sendButton.disabled = true;
    statusBox.textContent = "Thinking...";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                prompt: prompt,
                conversation_id: conversationId
            })
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Request failed");

        conversationId = data.conversation_id;
        addMessage(data.response, "assistant");
        statusBox.textContent = "Ready";
    } catch (error) {
        addMessage("Error: " + error.message, "assistant");
        statusBox.textContent = "Something went wrong";
    } finally {
        sendButton.disabled = false;
        promptBox.focus();
    }
});

promptBox.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        document.getElementById("chatForm").requestSubmit();
    }
});
</script>
</body>
</html>
"""


class ChatHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 100000:
                self.send_json({"error": "Invalid request size"}, 400)
                return

            data = json.loads(self.rfile.read(length))
            prompt = data.get("prompt", "").strip()
            conversation_id = data.get("conversation_id") or None

            if not prompt:
                self.send_json({"error": "Message cannot be empty"}, 400)
                return

            ai = OllamaAIProvider(conversation_id)
            answer = ai.generate_response(prompt)

            self.send_json({
                "response": answer,
                "conversation_id": ai.conversation_id
            })

        except Exception as error:
            self.send_json({"error": str(error)}, 500)

    def log_message(self, format, *args):
        print(f"[WEB] {args[0]}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ChatHandler)
    print("Personal AI Assistant running at http://localhost:8000")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
