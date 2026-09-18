"""Claude Code `UserPromptSubmit` hook.

Claude Code pipes a JSON object on stdin (session_id, transcript_path, cwd, prompt, ...).
Whatever we print as `additionalContext` is injected into Claude's context alongside the
prompt, so Claude sees "Suggested skill: X" before it starts working. `systemMessage` is
shown to the human in the transcript.

Rules of the road: never block the prompt, never crash, never take long.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from skill_router import catalog, skills_sh
from skill_router.context import build_state
from skill_router.router import Recommendation, route

LOG_PATH = Path.home() / ".cache" / "skill-router" / "decisions.jsonl"
MIN_PROMPT_CHARS = 12
DISABLE_ENV = "SKILL_ROUTER_DISABLE"
QUIET_ENV = "SKILL_ROUTER_QUIET"  # set to 1 to hide the systemMessage shown to the human


def should_skip(prompt: str) -> str | None:
    p = prompt.strip()
    if os.environ.get(DISABLE_ENV) == "1":
        return "disabled"
    if p.startswith("/"):
        return "already_a_skill_invocation"
    if not p or len(p) < MIN_PROMPT_CHARS:
        return "too_short"
    return None


def format_context(rec: Recommendation, remote: list[skills_sh.RemoteSkill], uncovered: list[str] | None = None) -> tuple[str, str]:
    """Return (additionalContext for Claude, short systemMessage for the human)."""
    tag = "skill-router" + (" (mock, no TYPESAFE_API_KEY)" if rec.source == "mock" else "")
    lines = [f"[{tag}] Jev classified this prompt as `{rec.task_kind}` "
             f"(confidence {rec.task_kind_confidence:.2f}); needs-a-skill probability {rec.needs_skill:.2f}."]
    human = ""
    if rec.should_suggest:
        p = rec.skill_probabilities.get(rec.skill or "", 0.0)
        lines.append(
            f"Suggested skill: `{rec.skill}` (probability {p:.2f}, confidence {rec.skill_confidence:.2f}). "
            f"If it fits the request, invoke it with the Skill tool before doing the work; if it does not, ignore this."
        )
        human = f"skill-router → /{rec.skill} ({p:.0%})"
        if rec.runners_up:
            alts = ", ".join(f"`{n}` ({p:.2f})" for n, p in rec.runners_up)
            lines.append(f"Also plausible: {alts}.")
            human += "  alt: " + ", ".join(n for n, _ in rec.runners_up)
    elif rec.skill and rec.runners_up:
        alts = ", ".join(f"`{n}` ({p:.2f})" for n, p in [(rec.skill, rec.skill_probabilities.get(rec.skill, 0.0)), *rec.runners_up])
        lines.append(f"No single installed skill stands out. Candidates if useful: {alts}.")
        human = "skill-router → unsure: " + ", ".join([rec.skill, *[n for n, _ in rec.runners_up]])
    else:
        lines.append("No installed skill clearly applies.")
    if remote:
        if uncovered:
            named = ", ".join(uncovered)
            lines.append(f"Caveat: the request names {named}, which `{rec.skill}` does not cover. skills.sh has more specific candidates:")
        else:
            lines.append(f"Nothing installed fits well, but skills.sh has candidates under topic `{rec.topic}`:")
        for r in remote:
            lines.append(f"  - {r.package}@{r.skill} ({r.installs} installs) → `{r.install_command}`  {r.url}")
        lines.append("Mention the top one to the user as an optional install; do not install without asking.")
        human = (human + "  " if human else "skill-router → ") + f"skills.sh: {remote[0].package}@{remote[0].skill}"
    return "\n".join(lines), human


def _log(entry: dict[str, Any]) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def run(payload: dict[str, Any], *, search_remote: bool = True) -> dict[str, Any] | None:
    """Pure function used by both the CLI and the tests. Returns the JSON to print, or None."""
    prompt = str(payload.get("prompt", ""))
    skip = should_skip(prompt)
    if skip:
        return None
    cwd = payload.get("cwd") or os.getcwd()
    state = build_state(prompt, cwd=cwd, transcript_path=payload.get("transcript_path"))
    skills = catalog.discover(cwd)
    rec = route(state, skills)
    remote: list[skills_sh.RemoteSkill] = []
    uncovered: list[str] = []
    if search_remote and rec.should_search_skills_sh and rec.topic:
        remote = skills_sh.find(skills_sh.build_query(prompt, rec.topic, rec.task_kind), limit=3)
    elif search_remote and rec.should_suggest:
        chosen = next((s.description for s in skills if s.name == rec.skill), "")
        uncovered = rec.uncovered_tech_terms(prompt, chosen)
        if uncovered:
            remote = skills_sh.find(skills_sh.build_query(prompt, rec.topic, rec.task_kind), limit=3)
    context, human = format_context(rec, remote, uncovered)
    _log({
        "ts": time.time(),
        "session_id": payload.get("session_id"),
        "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
        "prompt_head": prompt[:160],
        "cwd": cwd,
        "n_skills": len(skills),
        "recommendation": rec.to_dict(),
        "remote": [r.to_dict() for r in remote],
        "uncovered_tech_terms": uncovered,
    })
    out: dict[str, Any] = {
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context},
    }
    if human and os.environ.get(QUIET_ENV) != "1":
        out["systemMessage"] = human
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        out = run(payload)
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:  # noqa: BLE001 - a hook must never break the user's prompt
        _log({"ts": time.time(), "error": traceback.format_exc()[-2000:]})
    return 0
