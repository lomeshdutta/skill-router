"""Per-session state: the one-sentence goal captured at session start and what Jev said about it.

One JSON file per Claude Code session under ~/.cache/skill-router/sessions/. The id comes from
the hook's stdin (`session_id`), else the CLAUDE_SESSION_ID environment variable, else "manual".
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path.home() / ".cache" / "skill-router" / "sessions"
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def resolve_id(explicit: str | None = None) -> str:
    return _SAFE.sub("_", explicit or os.environ.get("CLAUDE_SESSION_ID") or "manual")[:80]


def path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{resolve_id(session_id)}.json"


def load(session_id: str) -> dict[str, Any] | None:
    try:
        return json.loads(path(session_id).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def save(session_id: str, data: dict[str, Any]) -> Path:
    p = path(session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**data, "saved_at": time.time()}, indent=1, default=str))
    return p


def clear(session_id: str) -> bool:
    try:
        path(session_id).unlink()
        return True
    except OSError:
        return False
