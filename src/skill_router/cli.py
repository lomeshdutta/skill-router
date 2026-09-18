"""Command-line entry point: `skill-router <command>`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from skill_router import catalog, hook, skills_sh
from skill_router.context import build_state
from skill_router.router import route, use_mock

HOOK_TIMEOUT_SECONDS = 20


def hook_settings_snippet(command: str) -> dict:
    return {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT_SECONDS}]}
            ]
        }
    }


def _default_hook_command() -> str:
    exe = Path(sys.argv[0]).resolve()
    if exe.name != "skill-router":
        exe = Path(sys.executable).parent / "skill-router"
    return f"{exe} hook"


def cmd_suggest(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt)
    cwd = args.cwd or os.getcwd()
    state = build_state(prompt, cwd=cwd)
    skills = catalog.discover(cwd)
    rec = route(state, skills)
    remote = skills_sh.find(skills_sh.build_query(prompt, rec.topic, rec.task_kind), limit=3) if (args.remote and rec.should_search_skills_sh and rec.topic) else []
    if args.json:
        print(json.dumps({"state": state, "recommendation": rec.to_dict(), "remote": [r.to_dict() for r in remote]}, indent=2))
        return 0
    ctx, human = hook.format_context(rec, remote)
    print(f"source={rec.source} model={rec.model} latency={rec.latency_ms}ms skills_considered={len(skills)} usage={rec.usage}")
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
    snippet = hook_settings_snippet(args.command or _default_hook_command())
    target = Path(args.settings).expanduser() if args.settings else Path(os.getcwd()) / ".claude" / "settings.json"
    if not args.write:
        print(f"# Add this to {target} (re-run with --write to do it):")
        print(json.dumps(snippet, indent=2))
        return 0
    existing = {}
    if target.exists():
        existing = json.loads(target.read_text() or "{}")
    hooks = existing.setdefault("hooks", {})
    ups = hooks.setdefault("UserPromptSubmit", [])
    if not any("skill-router" in h.get("command", "") for grp in ups for h in grp.get("hooks", [])):
        ups.extend(snippet["hooks"]["UserPromptSubmit"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"wrote hook to {target}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    p = hook.LOG_PATH
    if not p.exists():
        print(f"no log yet at {p}")
        return 0
    lines = p.read_text().splitlines()[-args.tail:]
    for line in lines:
        d = json.loads(line)
        if "error" in d:
            print(f"ERROR {d['error'].splitlines()[-1]}")
            continue
        r = d["recommendation"]
        print(f"{r['source']:4s} {r['task_kind']:18s} needs={r['needs_skill']:.2f} skill={r['skill'] or '-':28s} conf={r['skill_confidence']:.2f} {r['latency_ms']:5d}ms  {d['prompt_head'][:60]!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="skill-router", description="Predict which Claude Code skill a prompt needs (powered by Jev / TypeSafe AI).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("suggest", help="classify a prompt and print the suggestion")
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

    h = sub.add_parser("hook", help="run as a Claude Code UserPromptSubmit hook (JSON on stdin)")
    h.set_defaults(fn=cmd_hook)

    i = sub.add_parser("install-hook", help="print or write the hook config for Claude Code")
    i.add_argument("--settings", help="settings.json to modify (default: ./.claude/settings.json)")
    i.add_argument("--command", help="override the hook command")
    i.add_argument("--write", action="store_true")
    i.set_defaults(fn=cmd_install_hook)

    lg = sub.add_parser("log", help="show recent routing decisions")
    lg.add_argument("--tail", type=int, default=20)
    lg.set_defaults(fn=cmd_log)

    args = ap.parse_args(argv)
    if args.cmd in ("suggest",) and use_mock():
        print("note: running in MOCK mode (set TYPESAFE_API_KEY to use Jev)", file=sys.stderr)
    return args.fn(args)
