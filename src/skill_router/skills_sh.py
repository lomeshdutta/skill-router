"""Search the public skills.sh directory via the open-source `skills` CLI.

The skills.sh HTTP API requires a Vercel OIDC token, but `npx skills find <query>` works
anonymously, so we shell out to it and parse its text output. Results are cached on disk
because npx startup costs a couple of seconds.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "skill-router"
CACHE_TTL_SECONDS = 24 * 3600
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_LINE = re.compile(r"^(?P<pkg>[\w.-]+/[\w.-]+)@(?P<skill>[^\s]+(?: [^\s]+)*?)\s+(?P<installs>[\d.,]+[KM]?) installs?", re.M)
_URL = re.compile(r"https://skills\.sh/\S+")


@dataclass(frozen=True)
class RemoteSkill:
    package: str
    skill: str
    installs: str
    url: str

    @property
    def install_command(self) -> str:
        return f"npx skills add {self.package}@{self.skill}"

    def to_dict(self) -> dict:
        return asdict(self) | {"install_command": self.install_command}


def parse_find_output(text: str) -> list[RemoteSkill]:
    clean = _ANSI.sub("", text)
    results: list[RemoteSkill] = []
    blocks = clean.split("\n\n")
    for block in blocks:
        m = _LINE.search(block)
        if not m:
            continue
        u = _URL.search(block)
        results.append(RemoteSkill(m["pkg"], m["skill"].strip(), m["installs"], u.group(0) if u else ""))
    return results


def _cache_path(query: str) -> Path:
    key = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:80]
    return CACHE_DIR / f"find-{key}.json"


def find(query: str, limit: int = 5, timeout: float = 12.0) -> list[RemoteSkill]:
    cache = _cache_path(query)
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_SECONDS:
            return [RemoteSkill(**{k: v for k, v in d.items() if k != "install_command"}) for d in json.loads(cache.read_text())][:limit]
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    npx = shutil.which("npx")
    if not npx:
        return []
    try:
        proc = subprocess.run(
            [npx, "-y", "skills", "find", query],
            capture_output=True, text=True, timeout=timeout, env={"DISABLE_TELEMETRY": "1", "PATH": _path()},
        )
    except (OSError, subprocess.SubprocessError):
        return []
    results = parse_find_output(proc.stdout)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([r.to_dict() for r in results]))
    except OSError:
        pass
    return results[:limit]


def _path() -> str:
    import os
    return os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin")
