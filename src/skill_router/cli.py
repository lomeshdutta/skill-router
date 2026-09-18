"""Command-line entry point: `skill-router <command>`.

Session flow (v0.2):   session-start (hook)  →  intent set "<goal>"  →  intent show / clear
Legacy per-prompt flow: hook (opt-in UserPromptSubmit)
Tools:                  suggest, catalog, search, log, install-hook
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from skill_router import catalog, hook, session, skills_sh
from skill_router.context import build_state
from skill_router.router import OUTCOME_INSTALLED, OUTCOME_NONE, OUTCOME_SEARCH, Recommendation, route, use_mock

HOOK_TIMEOUT_SECONDS = 20
FIND_SKILLS_NAME = "find-skills"
FIND_SKILLS_INSTALL = "npx skills add vercel-labs/skills --skill find-skills -g"
SESSION_START_TIMEOUT_SECONDS = 10

SESSION_START_INSTRUCTION = (
    "[skill-router] Before starting real work in this session, establish the session goal once. "
    "If the user's first message makes it clear what they are trying to get done, infer a one-sentence "
    'goal from it. If it does not, ask exactly one question: "What are you trying to get done this '
    'session?" Then run `{exe} intent set "<one-sentence goal>"` and act on its output: it names '
    "installed skills to load, or tells you to search skills.sh with the find-skills skill, or says no "
    "skill is needed. Do not ask about the goal again this session; if the user pivots, they will run "
    "/intent themselves."
)


# --------------------------------------------------------------------------- helpers
def _exe() -> str:
    exe = Path(sys.argv[0]).resolve()
    if exe.name != "skill-router":
        exe = Path(sys.executable).parent / "skill-router"
    return str(exe)


def hook_settings_snippet(event: str, command: str) -> dict:
    timeout = SESSION_START_TIMEOUT_SECONDS if event == "SessionStart" else HOOK_TIMEOUT_SECONDS
    return {"hooks": {event: [{"hooks": [{"type": "command", "command": command, "timeout": timeout}]}]}}


def format_intent(rec: Recommendation, skills: list[catalog.SkillInfo], goal: str) -> str:
    """The text Claude relays to the user after `intent set`."""
    by_name = {s.name: s for s in skills}
    tag = "skill-router" + (" (mock, no TYPESAFE_API_KEY)" if rec.source == "mock" else "")
    head = f"[{tag}] Session goal: {goal}\nJev: task kind `{rec.task_kind}`, needs-a-skill {rec.needs_skill:.2f}."
    if rec.outcome == OUTCOME_INSTALLED:
        ranked = [(n, p) for n, p in rec.skill_probabilities.items() if n != "none" and p >= 0.05][:3]
        lines = [head, "Relevant installed skills for this session:"]
        for n, p in ranked:
            desc = (by_name[n].description if n in by_name else "").split(". ")[0][:110]
            lines.append(f"  /{n} (probability {p:.2f}) — {desc}")
        top = ranked[0][0] if ranked else rec.skill
        lines.append(f"Load /{top} with the Skill tool when the work starts. Do not install anything.")
        return "\n".join(lines)
    if rec.outcome == OUTCOME_SEARCH:
        best = f"{rec.skill} {rec.skill_probability:.2f}" if rec.skill else f"best {rec.best_local_probability:.2f}"
        lines = [head, f"No installed skill fits this goal ({best})."]
        if FIND_SKILLS_NAME in by_name:
            lines.append(f"Use the find-skills skill to search skills.sh for: {goal}")
        else:
            lines.append(
                "The find-skills skill is not installed, so skills.sh cannot be searched with a quality filter. "
                "Tell the user this, and offer the install command (run it only if they say yes):"
            )
            lines.append(f"  {FIND_SKILLS_INSTALL}")
            lines.append(f'Until then, `skill-router search "{goal}"` gives a raw, unfiltered list.')
        lines.append("Present what it finds; do not install anything without the user's explicit yes.")
        return "\n".join(lines)
    return f"{head}\nGeneral assistance is fine for this goal; no skill needed."


# --------------------------------------------------------------------------- commands
def cmd_session_start(_args: argparse.Namespace) -> int:
    """Claude Code SessionStart hook. Never raises, never blocks."""
    try:
        payload = json.load(sys.stdin)
        source = payload.get("source", "startup")
        sid = session.resolve_id(payload.get("session_id"))
        existing = session.load(sid) if source in ("resume", "fork") else None
        if existing and existing.get("goal"):
            text = (
                f"[skill-router] Session goal on record: {existing['goal']!r} → {existing.get('summary', '')}. "
                f'Run `{_exe()} intent set "<goal>"` only if the user\'s goal has changed.'
            )
        else:
            text = SESSION_START_INSTRUCTION.format(exe=_exe())
        sys.stdout.write(
            json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
        )
    except Exception:  # noqa: BLE001 - a hook must never break session start
        hook._log({"error": traceback.format_exc()[-2000:], "where": "session-start"})
    return 0


def cmd_intent(args: argparse.Namespace) -> int:
    sid = session.resolve_id(args.session)
    if args.action == "show":
        data = session.load(sid)
        print(json.dumps(data, indent=2) if data else f"no goal recorded for session {sid!r}")
        return 0
    if args.action == "clear":
        print("cleared" if session.clear(sid) else f"nothing to clear for session {sid!r}")
        return 0
    goal = " ".join(args.goal).strip()
    if not goal:
        print('usage: skill-router intent set "<one-sentence goal>"', file=sys.stderr)
        return 2
    cwd = args.cwd or os.getcwd()
    try:
        skills = catalog.discover(cwd)
        rec = route(build_state(goal, cwd=cwd, goal=True), skills)
    except Exception as exc:  # noqa: BLE001 - Jev outage, bad key, proxy: never break the session
        hook._log({"error": traceback.format_exc()[-2000:], "where": "intent", "goal": goal})
        reason = exc.__class__.__name__
        text = (
            f"[skill-router] Could not get a routing decision ({reason}); proceeding without a suggestion. "
            "Load skills by hand if you know one applies. Details in ~/.cache/skill-router/decisions.jsonl."
        )
        session.save(sid, {"goal": goal, "cwd": cwd, "outcome": "error", "summary": f"error: {reason}"})
        print(json.dumps({"goal": goal, "outcome": "error", "text": text}, indent=2) if args.json else text)
        return 0
    text = format_intent(rec, skills, goal)
    summary = {
        OUTCOME_INSTALLED: f"load /{rec.skill}",
        OUTCOME_SEARCH: "search skills.sh via find-skills",
        OUTCOME_NONE: "no skill needed",
    }[rec.outcome]
    session.save(
        sid, {"goal": goal, "cwd": cwd, "outcome": rec.outcome, "summary": summary, "recommendation": rec.to_dict()}
    )
    hook._log(
        {
            "session_id": sid,
            "kind": "intent",
            "goal": goal,
            "cwd": cwd,
            "n_skills": len(skills),
            "recommendation": rec.to_dict(),
        }
    )
    if args.json:
        print(
            json.dumps({"goal": goal, "outcome": rec.outcome, "recommendation": rec.to_dict(), "text": text}, indent=2)
        )
    else:
        print(text)
    return 0


def cmd_suggest(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt)
    cwd = args.cwd or os.getcwd()
    state = build_state(prompt, cwd=cwd)
    skills = catalog.discover(cwd)
    rec = route(state, skills)
    remote = []
    if args.remote and rec.should_search_skills_sh and rec.topic:
        remote = skills_sh.find(skills_sh.build_query(prompt, rec.topic, rec.task_kind), limit=3)
    if args.json:
        print(
            json.dumps(
                {"state": state, "recommendation": rec.to_dict(), "remote": [r.to_dict() for r in remote]}, indent=2
            )
        )
        return 0
    ctx, human = hook.format_context(rec, remote)
    print(
        f"source={rec.source} model={rec.model} latency={rec.latency_ms}ms skills_considered={len(skills)} usage={rec.usage}"
    )
    print(ctx)
    if human:
        print(f"\n{human}")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    skills = catalog.discover(args.cwd or os.getcwd())
    if args.json:
        print(json.dumps([s.to_dict() for s in skills], indent=2))
        return 0
    for s in skills:
        print(f"{s.scope:8s} {s.name:42s} {s.description[:80]}")
    print(f"\n{len(skills)} skills", file=sys.stderr)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    for r in skills_sh.find(" ".join(args.query), limit=args.limit):
        print(f"{r.package}@{r.skill:40s} {r.installs:>8s} installs   {r.install_command}")
    return 0


def cmd_hook(_args: argparse.Namespace) -> int:
    return hook.main()


def cmd_install_hook(args: argparse.Namespace) -> int:
    sub = "session-start" if args.event == "SessionStart" else "hook"
    snippet = hook_settings_snippet(args.event, args.command or f"{_exe()} {sub}")
    target = Path(args.settings).expanduser() if args.settings else Path(os.getcwd()) / ".claude" / "settings.json"
    if not args.write:
        print(f"# Add this to {target} (re-run with --write to do it):")
        print(json.dumps(snippet, indent=2))
        return 0
    existing = json.loads(target.read_text() or "{}") if target.exists() else {}
    groups = existing.setdefault("hooks", {}).setdefault(args.event, [])
    if not any("skill-router" in h.get("command", "") for g in groups for h in g.get("hooks", [])):
        groups.extend(snippet["hooks"][args.event])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"wrote {args.event} hook to {target}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    p = hook.LOG_PATH
    if not p.exists():
        print(f"no log yet at {p}")
        return 0
    for line in p.read_text().splitlines()[-args.tail :]:
        d = json.loads(line)
        if "error" in d:
            print(f"ERROR {d['error'].splitlines()[-1]}")
            continue
        r = d["recommendation"]
        head = d.get("goal") or d.get("prompt_head", "")
        print(
            f"{d.get('kind', 'prompt'):6s} {r['source']:4s} {r['task_kind']:18s} needs={r['needs_skill']:.2f} skill={r['skill'] or '-':28s} conf={r['skill_confidence']:.2f} {r['latency_ms']:5d}ms  {head[:60]!r}"
        )
    return 0


# --------------------------------------------------------------------------- parser
def _add_intent_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["set", "show", "clear"])
    parser.add_argument("goal", nargs="*")
    parser.add_argument("--session", help="session id (default: $CLAUDE_SESSION_ID or 'manual')")
    parser.add_argument("--cwd")
    parser.add_argument("--json", action="store_true")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "intent" and not any(a in ("-h", "--help") for a in argv):
        # Options and the free-text goal may come in any order (`intent set --json "goal"` or
        # `intent set "goal" --json`). argparse only guarantees that with parse_intermixed_args,
        # which does not work through subparsers, so the intent command gets its own parser.
        intent_parser = argparse.ArgumentParser(prog="skill-router intent")
        _add_intent_arguments(intent_parser)
        args = intent_parser.parse_intermixed_args(argv[1:])
        if args.action == "set" and use_mock():
            print("note: running in MOCK mode (set TYPESAFE_API_KEY to use Jev)", file=sys.stderr)
        return cmd_intent(args)

    ap = argparse.ArgumentParser(
        prog="skill-router",
        description="Predict which Claude Code skill a session needs (powered by Jev / TypeSafe AI).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    ss = sub.add_parser("session-start", help="Claude Code SessionStart hook (JSON on stdin)")
    ss.set_defaults(fn=cmd_session_start)

    it = sub.add_parser("intent", help="set, show, or clear the session goal and get a routing decision")
    _add_intent_arguments(it)
    it.set_defaults(fn=cmd_intent)

    s = sub.add_parser("suggest", help="classify one prompt (legacy per-prompt routing)")
    s.add_argument("prompt", nargs="+")
    s.add_argument("--cwd")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-remote", dest="remote", action="store_false", help="skip the skills.sh lookup")
    s.set_defaults(fn=cmd_suggest)

    c = sub.add_parser("catalog", help="list the installed skills Jev chooses from")
    c.add_argument("--cwd")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_catalog)

    f = sub.add_parser("search", help="search skills.sh via `npx skills find`")
    f.add_argument("query", nargs="+")
    f.add_argument("--limit", type=int, default=8)
    f.set_defaults(fn=cmd_search)

    h = sub.add_parser("hook", help="legacy UserPromptSubmit hook (JSON on stdin); opt-in")
    h.set_defaults(fn=cmd_hook)

    i = sub.add_parser("install-hook", help="print or write the hook config for Claude Code")
    i.add_argument("--event", choices=["SessionStart", "UserPromptSubmit"], default="SessionStart")
    i.add_argument("--settings", help="settings.json to modify (default: ./.claude/settings.json)")
    i.add_argument("--command", help="override the hook command")
    i.add_argument("--write", action="store_true")
    i.set_defaults(fn=cmd_install_hook)

    lg = sub.add_parser("log", help="show recent routing decisions")
    lg.add_argument("--tail", type=int, default=20)
    lg.set_defaults(fn=cmd_log)

    args = ap.parse_args(argv)
    if args.cmd == "suggest" and use_mock():
        print("note: running in MOCK mode (set TYPESAFE_API_KEY to use Jev)", file=sys.stderr)
    return args.fn(args)
