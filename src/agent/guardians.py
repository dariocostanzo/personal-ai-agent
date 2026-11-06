"""Conservative local health checks; no command execution or destructive repair."""

import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from src.agent import agent_state

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LOG_DIR = DATA_DIR.parent / "logs"
DISK_WARNING_PERCENT = int(os.getenv("GUARDIAN_DISK_WARNING_PERCENT", "90"))


def _check_disk():
    usage = shutil.disk_usage(DATA_DIR)
    used_percent = round(usage.used / usage.total * 100)
    status = "attention" if used_percent >= DISK_WARNING_PERCENT else "healthy"
    details = f"{used_percent}% used; {usage.free // (1024 ** 3)} GiB free."
    return status, details


def _check_directories():
    repaired = []
    for directory in (DATA_DIR, LOG_DIR):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            repaired.append(directory.name)
    details = "Required local directories are available."
    if repaired:
        details = "Safely recreated missing directories: " + ", ".join(repaired) + "."
    return "healthy", details


def _check_service(name, url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "attention", "Configured service URL is invalid."
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            status = "healthy" if 200 <= response.status < 400 else "attention"
            return status, f"HTTP status {response.status}."
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return "attention", f"Service unavailable: {error}"


def _check_process(process_name):
    proc = Path("/proc")
    if not proc.is_dir():
        return "attention", "Process checks are unavailable on this operating system."
    expected = process_name.casefold()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "comm").read_text(encoding="utf-8").strip().casefold()
        except (OSError, UnicodeError):
            continue
        if command == expected:
            return "healthy", f"Process {process_name} is running (PID {entry.name})."
    return "attention", f"Process {process_name} was not found."


def run_checks():
    checks = [
        ("Local data and log directories", *_check_directories()),
        ("Disk space", *_check_disk()),
        ("Ollama HTTP API", *_check_service(
            "Ollama HTTP API",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/api/tags",
        )),
    ]
    process_names = [
        name.strip() for name in os.getenv("GUARDIAN_PROCESSES", "ollama").split(",")
        if name.strip()
    ]
    checks.extend((f"Process: {name}", *_check_process(name))
                  for name in process_names)
    with agent_state.connect() as connection:
        sources = connection.execute(
            "SELECT name, url FROM guardian_sources WHERE enabled = 1 ORDER BY id"
        ).fetchall()
    checks.extend(
        (row["name"], *_check_service(row["name"], row["url"])) for row in sources
    )
    attention = []
    for name, status, details in checks:
        agent_state.add_guardian_check(name, status, details)
        if status == "attention":
            attention.append(name)
    if attention:
        agent_state.add_decision(
            "guardian_attention", ", ".join(attention),
            "A configured local health check needs human attention.",
        )
    return {"checks": agent_state.list_guardian_checks(len(checks)),
            "needs_attention": bool(attention)}


def add_service(name, url):
    name = name.strip() if isinstance(name, str) else ""
    url = url.strip() if isinstance(url, str) else ""
    parsed = urlsplit(url)
    if not name or len(name) > 160:
        raise ValueError("Guardian check name cannot be empty or exceed 160 characters.")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Guardian checks need a valid http or https URL.")
    with agent_state.connect() as connection:
        connection.execute(
            "INSERT INTO guardian_sources (name, url) VALUES (?, ?)",
            (name, url),
        )
