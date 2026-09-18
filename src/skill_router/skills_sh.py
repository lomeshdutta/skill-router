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
_LINE = re.compile(
    r"^(?P<pkg>[\w.-]+/[\w.-]+)@(?P<skill>[^\s]+(?: [^\s]+)*?)\s+(?P<installs>[\d.,]+[KM]?) installs?", re.M
)
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


# Words that carry no search signal even when capitalised (sentence starts, common verbs/nouns).
_QUERY_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "with",
    "this",
    "that",
    "these",
    "those",
    "my",
    "our",
    "your",
    "in",
    "on",
    "to",
    "of",
    "from",
    "into",
    "using",
    "use",
    "set",
    "up",
    "add",
    "build",
    "write",
    "make",
    "create",
    "review",
    "deploy",
    "generate",
    "help",
    "me",
    "we",
    "i",
    "it",
    "is",
    "are",
    "each",
    "all",
    "page",
    "app",
    "project",
    "product",
    "description",
    "problems",
    "policies",
    "queries",
    "screens",
    "second",
    "seconds",
    "first",
    "new",
    "slow",
    "fast",
    "following",
    "questions",
    "over",
    "docs",
}
# Lower-case technology/vendor words worth keeping even when the user didn't capitalise them.
_TECH_HINTS = {
    "postgres",
    "postgresql",
    "mysql",
    "sqlite",
    "redis",
    "mongodb",
    "supabase",
    "neon",
    "prisma",
    "drizzle",
    "react",
    "nextjs",
    "next.js",
    "vue",
    "svelte",
    "angular",
    "remix",
    "astro",
    "tailwind",
    "shadcn",
    "shadcn/ui",
    "expo",
    "flutter",
    "swift",
    "kotlin",
    "android",
    "ios",
    "electron",
    "tauri",
    "docker",
    "kubernetes",
    "k8s",
    "aks",
    "eks",
    "gke",
    "terraform",
    "aws",
    "azure",
    "gcp",
    "vercel",
    "netlify",
    "cloudflare",
    "fly.io",
    "heroku",
    "railway",
    "render",
    "github",
    "gitlab",
    "ci",
    "cd",
    "python",
    "typescript",
    "javascript",
    "node",
    "rust",
    "go",
    "golang",
    "java",
    "ruby",
    "rails",
    "django",
    "fastapi",
    "flask",
    "laravel",
    "php",
    "graphql",
    "grpc",
    "rest",
    "openapi",
    "stripe",
    "twilio",
    "sendgrid",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "langchain",
    "langgraph",
    "adk",
    "mcp",
    "rag",
    "llm",
    "agent",
    "remotion",
    "ffmpeg",
    "figma",
    "storybook",
    "playwright",
    "cypress",
    "jest",
    "vitest",
    "pytest",
    "testing",
    "video",
    "audio",
    "image",
    "seo",
    "analytics",
    "posthog",
    "segment",
    "mixpanel",
    "notion",
    "slack",
    "lark",
    "salesforce",
    "hubspot",
    "shopify",
    "wordpress",
    "webflow",
    "framer",
    "unity",
    "unreal",
    "godot",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9.+#/-]*")


def extract_tech_terms(prompt: str, limit: int = 4) -> list[str]:
    """Pull vendor/technology words out of a prompt: capitalised proper nouns (not at sentence
    start) plus known lower-case tech words. Order preserved, duplicates dropped."""
    terms: list[str] = []
    seen: set[str] = set()
    sentence_start = True
    for raw in _WORD_RE.findall(prompt):
        word = raw.strip(".,;:!?'\"")
        low = re.sub(r"'s$", "", word.lower())
        looks_like_url = (
            "://" in low or low.startswith("www.") or re.search(r"\.(com|org|net|io|ai|dev|sh|app)(/|$)", low)
        ) and low not in _TECH_HINTS
        if not word or low in _QUERY_STOP or looks_like_url:
            sentence_start = raw.endswith((".", "?", "!"))
            continue
        is_proper = (
            word[0].isupper()
            and not sentence_start
            and len(word) > 1
            and not word.isupper()
            or (word.isupper() and 2 <= len(word) <= 5)
        )
        if (is_proper or low in _TECH_HINTS) and low not in seen:
            seen.add(low)
            terms.append(low)
        sentence_start = raw.endswith((".", "?", "!"))
        if len(terms) >= limit:
            break
    return terms


def build_query(prompt: str, topic: str | None, task_kind: str | None) -> str:
    """The query sent to `npx skills find`. Tech terms first; Jev's topic as a tie-breaker;
    fall back to topic + task kind when the prompt names nothing specific."""
    terms = extract_tech_terms(prompt)
    if terms:
        parts = terms[:3]
        if topic and topic not in parts and len(parts) < 3:
            parts.append(topic)
        return " ".join(parts)
    return " ".join(x for x in [topic, (task_kind or "").replace("_", " ")] if x).strip()


def _cache_path(query: str) -> Path:
    key = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:80]
    return CACHE_DIR / f"find-{key}.json"


def find(query: str, limit: int = 5, timeout: float = 12.0) -> list[RemoteSkill]:
    cache = _cache_path(query)
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_SECONDS:
            return [
                RemoteSkill(**{k: v for k, v in d.items() if k != "install_command"})
                for d in json.loads(cache.read_text())
            ][:limit]
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    npx = shutil.which("npx")
    if not npx:
        return []
    try:
        proc = subprocess.run(
            [npx, "-y", "skills", "find", query],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"DISABLE_TELEMETRY": "1", "PATH": _path()},
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
