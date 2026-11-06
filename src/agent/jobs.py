"""In-process periodic work for the local web-server process."""

import os
import threading
import time

from src.agent import guardians, news
from src.agent.logger import logger

_started = False
_lock = threading.Lock()


def _run_logged(label, operation):
    try:
        operation()
    except Exception:
        logger.exception("Scheduled %s failed.", label)


def _worker():
    refresh_seconds = max(5, int(os.getenv("NEWS_REFRESH_MINUTES", "60")) * 60)
    full_refresh_seconds = max(
        refresh_seconds, int(os.getenv("NEWS_FULL_REFRESH_HOURS", "24")) * 60 * 60
    )
    guardian_seconds = max(5, int(os.getenv("GUARDIAN_CHECK_MINUTES", "15")) * 60)
    next_news = next_guardian = 0.0
    next_full = 0.0
    while True:
        now = time.monotonic()
        if now >= next_news:
            full = next_full == 0.0 or now >= next_full
            _run_logged("news digest", lambda: news.run_digest(full=full))
            next_news = time.monotonic() + refresh_seconds
            if full:
                next_full = time.monotonic() + full_refresh_seconds
        if now >= next_guardian:
            _run_logged("guardian checks", guardians.run_checks)
            next_guardian = time.monotonic() + guardian_seconds
        time.sleep(min(60, max(1, min(next_news - time.monotonic(),
                                     next_guardian - time.monotonic()))))


def start_background_jobs():
    global _started
    if os.getenv("AGENT_SCHEDULER_ENABLED", "true").casefold() not in ("1", "true", "yes"):
        return False
    news.seed_sources_from_environment()
    with _lock:
        if _started:
            return False
        thread = threading.Thread(target=_worker, name="personal-agent-jobs", daemon=True)
        thread.start()
        _started = True
    return True
