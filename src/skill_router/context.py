"""Build the `state` Jev evaluates: the prompt plus cheap signals about the session.

Everything here must be fast (the hook runs on every prompt) and must never raise.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".cache"}
MARKER_FILES = [
    "CLAUDE.md", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod",
    "Dockerfile", "docker-compose.yml", "next.config.js", "next.config.ts", "vite.config.ts",
    "tsconfig.json", "Makefile", ".github", "prisma", "supabase",
]
MAX_RECENT_PROMPTS = 3
MAX_PROMPT_CHARS = 400


def _language_mix(root: Path, max_files: int = 400) -> dict[str, int]:
    counts: Counter[str] = Counter()
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= 2:
            dirnames[:] = []
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext:
                counts[ext] += 1
                seen += 1
                if seen >= max_files:
                    return dict(counts.most_common(8))
    return dict(counts.most_common(8))


def _git_branch(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=1.5,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _claude_md_head(root: Path, limit: int = 500) -> str | None:
    for p in [root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"]:
        try:
            return " ".join(p.read_text(errors="ignore")[:limit].split())
        except OSError:
            continue
    return None


def _message_text(msg: Any) -> str:
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(parts)
    return ""


def recent_user_prompts(transcript_path: str | None, exclude: str = "") -> list[str]:
    """Last few things the user typed, oldest first. Tool results and system text are skipped."""
    if not transcript_path:
        return []
    try:
        lines = Path(transcript_path).read_text(errors="ignore").splitlines()
    except OSError:
        return []
    prompts: list[str] = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") != "user":
            continue
        text = _message_text(rec.get("message", {})).strip()
        if not text or text.startswith("<") or "tool_result" in text[:40] or text == exclude.strip():
            continue
        prompts.append(text[:MAX_PROMPT_CHARS])
        if len(prompts) >= MAX_RECENT_PROMPTS:
            break
    return list(reversed(prompts))


def build_state(prompt: str, cwd: str | None = None, transcript_path: str | None = None) -> dict[str, Any]:
    root = Path(cwd or os.getcwd())
    state: dict[str, Any] = {"user_prompt": prompt.strip()}
    try:
        project: dict[str, Any] = {
            "directory": root.name,
            "path": str(root),
            "languages_by_file_extension": _language_mix(root),
            "marker_files_present": [m for m in MARKER_FILES if (root / m).exists()],
        }
        branch = _git_branch(root)
        if branch:
            project["git_branch"] = branch
        head = _claude_md_head(root)
        if head:
            project["claude_md_excerpt"] = head
        state["project"] = project
    except Exception:  # noqa: BLE001 - context is best-effort
        state["project"] = {"directory": root.name}
    recent = recent_user_prompts(transcript_path, exclude=prompt)
    if recent:
        state["earlier_prompts_this_session"] = recent
    return state
