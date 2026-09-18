"""Discover the skills installed for Claude Code on this machine.

A *skill* is a folder containing a SKILL.md whose YAML front matter has a `name` and a
`description`. Claude Code loads them from three places:

  user     ~/.claude/skills/<name>/SKILL.md          (available in every project)
  project  <project>/.claude/skills/<name>/SKILL.md  (only inside that project)
  plugins  ~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/skills/<name>/SKILL.md
  app      the desktop app's bundled skills (pptx, docx, xlsx, pdf, ...) under
           ~/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/
  builtin  skills compiled into Claude Code itself (code-review, simplify, ...). These have
           no SKILL.md on disk, so they are listed statically in BUILTIN_SKILLS below.

Skills switched "off" in ~/.claude/settings.json (`skillOverrides`) are excluded, as are
plugins that are not enabled (`enabledPlugins`).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
APP_SKILLS_GLOB = Path.home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions" / "skills-plugin"

# Claude Code built-ins. Descriptions paraphrase the harness's own skill listing.
BUILTIN_SKILLS: dict[str, str] = {
    "code-review": "Review the current diff, a PR, branch, or path for correctness bugs and simplification, reuse, or efficiency cleanups. Use for 'review my changes', 'check this PR', 'find bugs in my diff'.",
    "simplify": "Review changed code for reuse, simplification, efficiency, and clarity cleanups, then apply the fixes. Quality only, not bug hunting.",
    "security-review": "Security review of the current changes or codebase: secrets, injection, auth, unsafe patterns.",
    "init": "Create or refresh a CLAUDE.md for the current project by analyzing the codebase.",
    "loop": "Run a prompt or slash command repeatedly on an interval, poll for status, or babysit a long process.",
    "schedule": "Create or manage scheduled cloud agents (routines) that run on a cron schedule, or a one-time run at a set time.",
    "run": "Launch and drive the project's app to see a change working: run, start, or screenshot the app.",
    "claude-api": "Reference for the Claude API and Anthropic SDK: model ids, pricing, params, streaming, tool use, caching, migration.",
    "update-config": "Configure Claude Code settings.json: hooks, permissions, env vars, automated 'whenever X do Y' behaviors.",
    "keybindings-help": "Customize Claude Code keyboard shortcuts and ~/.claude/keybindings.json.",
    "fewer-permission-prompts": "Scan transcripts for common read-only commands and add an allowlist to reduce permission prompts.",
    "design": "Create a multi-artboard design canvas: UI mockups, landing pages, posters, flyers, social graphics.",
    "dataviz": "Guidance for any chart, graph, plot, dashboard, or data visualization in any medium.",
}


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    scope: str  # "project" | "user" | "plugin"
    path: str

    def to_dict(self) -> dict:
        return asdict(self)


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.S)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Tiny YAML-ish parser: handles `key: value`, quoted values, and `>`/`|` blocks.

    We avoid a YAML dependency because SKILL.md front matter is nearly always flat.
    """
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val in (">", "|", ">-", "|-", ""):
            block: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or lines[i] == ""):
                block.append(lines[i].strip())
                i += 1
            out[key] = " ".join(b for b in block if b).strip()
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
        i += 1
    return out


def _first_paragraph(text: str) -> str:
    body = _FRONTMATTER.sub("", text, count=1).strip()
    for para in re.split(r"\n\s*\n", body):
        p = " ".join(para.split())
        if p and not p.startswith("#"):
            return p[:300]
    return ""


def _load_settings() -> dict:
    try:
        return json.loads((CLAUDE_HOME / "settings.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _skill_from_file(path: Path, scope: str) -> SkillInfo | None:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return None
    fm = parse_frontmatter(text)
    name = fm.get("name") or path.parent.name
    desc = fm.get("description") or _first_paragraph(text)
    return SkillInfo(name=name, description=desc, scope=scope, path=str(path))


def _project_roots(cwd: Path) -> list[Path]:
    """cwd and its ancestors below the home directory.

    Claude Code picks up .claude/skills from the project and its parents, but the home
    directory's ~/.claude/skills is the *user* scope and is scanned separately.
    """
    home = Path.home().resolve()
    user_dir = (CLAUDE_HOME / "skills").resolve()
    roots = []
    for p in [cwd, *cwd.parents]:
        if p == home or p == home.parent or p == Path(p.anchor):
            break
        d = p / ".claude" / "skills"
        if d.is_dir() and d.resolve() != user_dir:
            roots.append(d)
    return roots


def _plugin_skill_files(settings: dict) -> list[Path]:
    enabled = settings.get("enabledPlugins", {}) or {}
    cache = CLAUDE_HOME / "plugins" / "cache"
    if not cache.is_dir():
        return []
    files: list[Path] = []
    for skill_md in cache.glob("*/*/*/skills/*/SKILL.md"):
        rel = skill_md.relative_to(cache).parts  # marketplace, plugin, version, skills, name, SKILL.md
        key = f"{rel[1]}@{rel[0]}"
        if enabled.get(key) is True:
            files.append(skill_md)
    return files


def _app_skill_files() -> list[Path]:
    """Bundled desktop-app skills. The path contains session ids, so take the newest folder."""
    if not APP_SKILLS_GLOB.is_dir():
        return []
    dirs = [d for d in APP_SKILLS_GLOB.glob("*/*/skills") if d.is_dir()]
    if not dirs:
        return []
    newest = max(dirs, key=lambda d: d.stat().st_mtime)
    return sorted(newest.glob("*/SKILL.md"))


def discover(cwd: str | os.PathLike | None = None) -> list[SkillInfo]:
    """Return installed, enabled skills. Project shadows user shadows plugin shadows app shadows builtin."""
    cwd_path = Path(cwd or os.getcwd()).resolve()
    settings = _load_settings()
    overrides = settings.get("skillOverrides", {}) or {}

    found: dict[str, SkillInfo] = {}

    def add(path: Path, scope: str) -> None:
        info = _skill_from_file(path, scope)
        if info is None or overrides.get(info.name) == "off":
            return
        found.setdefault(info.name, info)

    for root in _project_roots(cwd_path):
        for f in sorted(root.glob("*/SKILL.md")):
            add(f, "project")
    for f in sorted((CLAUDE_HOME / "skills").glob("*/SKILL.md")):
        add(f, "user")
    for f in sorted(_plugin_skill_files(settings)):
        add(f, "plugin")
    for f in _app_skill_files():
        add(f, "app")
    for name, desc in BUILTIN_SKILLS.items():
        if overrides.get(name) != "off":
            found.setdefault(name, SkillInfo(name=name, description=desc, scope="builtin", path=""))

    return sorted(found.values(), key=lambda s: (s.scope != "project", s.name))
