"""Bounded, local full-text search over a user-designated documents folder."""
import os
import re
from pathlib import Path

PROJECT_DATA = Path(__file__).resolve().parents[2] / "data"
DOCUMENTS_DIR = Path(
    os.environ.get("AGENT_DOCUMENTS_DIR", PROJECT_DATA / "documents")
).expanduser()
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".rst"}
MAX_FILE_BYTES = 1_000_000
MAX_FILES_SCANNED = 2_000
MAX_RESULTS = 5
MAX_SNIPPET_CHARS = 500
STOP_WORDS = {
    "a", "an", "and", "are", "about", "document", "documents", "find",
    "for", "in", "me", "my", "of", "please", "search", "the", "to",
}


def _query_terms(query):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Document search cannot be empty.")
    terms = [
        term for term in re.findall(r"[\w'-]+", query.casefold())
        if term not in STOP_WORDS
    ]
    if not terms:
        raise ValueError("Add a few specific words to search your documents.")
    return list(dict.fromkeys(terms))


def _candidate_files(root):
    scanned = 0
    for current, directories, filenames in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if not name.startswith(".")
            and not (Path(current) / name).is_symlink()
        )
        for filename in sorted(filenames):
            scanned += 1
            if scanned > MAX_FILES_SCANNED:
                return
            path = Path(current) / filename
            if (filename.startswith(".") or path.is_symlink()
                    or path.suffix.casefold() not in SUPPORTED_EXTENSIONS):
                continue
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
                if resolved.stat().st_size <= MAX_FILE_BYTES:
                    yield resolved
            except (OSError, ValueError):
                continue


def search_documents(query, root=None, max_results=MAX_RESULTS):
    """Search only supported, small text files in the configured folder."""
    terms = _query_terms(query)
    folder = Path(root or DOCUMENTS_DIR).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    limit = max(1, min(int(max_results), MAX_RESULTS))
    matches = []

    for path in _candidate_files(folder):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        folded = text.casefold()
        found = [term for term in terms if term in folded]
        if not found:
            continue
        matching_line = next(
            (line.strip() for line in text.splitlines()
             if any(term in line.casefold() for term in found)),
            text.strip(),
        )
        if len(matching_line) > MAX_SNIPPET_CHARS:
            matching_line = matching_line[:MAX_SNIPPET_CHARS].rstrip() + "…"
        matches.append({
            "path": path.relative_to(folder).as_posix(),
            "score": sum(folded.count(term) for term in found),
            "matched_terms": found,
            "snippet": matching_line,
        })

    matches.sort(key=lambda result: (-result["score"], result["path"].casefold()))
    return matches[:limit]
