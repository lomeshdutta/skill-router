"""Eval harness for skill-router. Usage: uv run python evals/run_eval.py [--no-remote]

Installed cases: did Jev rank the expected skill first / top-3, and would the hook have spoken?
Not-installed cases: did the router avoid a false local suggestion, trigger the skills.sh search,
and does the expected skill show up in the results? Two search queries are compared:
  topic query  = what the hook sends today  ("databases build feature")
  prompt query = the user's prompt itself    (skills.sh does semantic search on multi-word text)
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from skill_router import catalog, skills_sh  # noqa: E402
from skill_router.context import build_state  # noqa: E402
from skill_router.router import route  # noqa: E402

ROOT = Path(__file__).resolve().parent
CASES = json.loads((ROOT / "cases.json").read_text())
CWD = "/Users/dutta/projects/sandbox/test1"
REMOTE = "--no-remote" not in sys.argv


def remote_hit(expect: str, results: list[skills_sh.RemoteSkill]) -> int | None:
    pkg, _, skill = expect.partition("@")
    for i, r in enumerate(results, 1):
        if r.package == pkg and (r.skill == skill or not skill):
            return i
    for i, r in enumerate(results, 1):  # same repo, different skill still counts as "found the repo"
        if r.package == pkg:
            return -i
    return None


def main() -> None:
    skills = catalog.discover(CWD)
    names = {s.name for s in skills}
    lines: list[str] = [f"# skill-router eval, {date.today()}", "", f"Catalog: {len(skills)} skills. Model: real Jev unless noted.", ""]
    lat: list[int] = []
    tok: list[int] = []

    # ---------------------------------------------------------------- installed
    lines += ["## Installed skills (10)", "", "| expected | Jev top-1 | p | conf | needs | spoke? | top-3 | extra skills.sh search? | verdict |", "|---|---|---|---|---|---|---|---|---|"]
    top1 = top3 = spoke_right = extra_fired = 0
    by_name = {s.name: s for s in skills}
    for c in CASES["installed"]:
        assert c["expect"] in names, f"{c['expect']} not in catalog"
        rec = route(build_state(c["prompt"], cwd=CWD), skills)
        lat.append(rec.latency_ms); tok.append(rec.usage.get("input_tokens") or 0)
        ranked = list(rec.skill_probabilities)
        hit1 = rec.skill == c["expect"]; hit3 = c["expect"] in ranked[:3]
        top1 += hit1; top3 += hit3
        spoke = rec.should_suggest and hit1
        spoke_right += spoke
        verdict = "PASS" if spoke else ("top-3" if hit3 else "MISS")
        unc: list[str] = []  # v0.1's second search path was removed in v0.2; column kept for comparability
        lines.append(f"| {c['expect']} | {rec.skill or 'none'} | {rec.skill_probability:.2f} | {rec.skill_confidence:.2f} | {rec.needs_skill:.2f} | {'yes' if rec.should_suggest else 'no'} | {', '.join(ranked[:3])} | {('YES: ' + ', '.join(unc)) if unc else 'no'} | {verdict} |")
        print(f"[installed] {c['expect']:18s} -> {rec.skill or 'none':18s} p={rec.skill_probability:.2f} {verdict}", flush=True)
    lines += ["", f"**Top-1: {top1}/10 · Top-3: {top3}/10 · Hook spoke with the right skill: {spoke_right}/10 · Unwanted extra skills.sh search: {extra_fired}/10**", ""]

    # ------------------------------------------------------------ not installed
    lines += ["## Not installed, should fall through to skills.sh (10)", "", "| expected on skills.sh | local pick | p | local suggest? | tech named (Jev) | search fired? | topic | rank via topic query | rank via prompt query | rank via tech query | tech query |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    fp = fired = hit_topic = hit_prompt = hit_tech = 0
    by_name = {s.name: s for s in skills}
    for c in CASES["not_installed"]:
        rec = route(build_state(c["prompt"], cwd=CWD), skills)
        lat.append(rec.latency_ms); tok.append(rec.usage.get("input_tokens") or 0)
        false_pos = rec.should_suggest
        unc: list[str] = []
        fires = rec.should_search_skills_sh
        fp += false_pos; fired += fires
        r_topic = r_prompt = r_tech = None
        q_tech = skills_sh.build_query(c["prompt"], rec.topic, rec.task_kind)
        if REMOTE:
            q_topic = f"{rec.topic} {rec.task_kind.replace('_', ' ')}"
            r_topic = remote_hit(c["expect"], skills_sh.find(q_topic, limit=5))
            r_prompt = remote_hit(c["expect"], skills_sh.find(c["prompt"], limit=5))
            r_tech = remote_hit(c["expect"], skills_sh.find(q_tech, limit=5))
        hit_topic += r_topic is not None; hit_prompt += r_prompt is not None; hit_tech += r_tech is not None
        fmt = lambda r: "-" if r is None else (f"#{r}" if r > 0 else f"repo #{-r}")
        lines.append(f"| {c['expect']} | {rec.skill or 'none'} | {rec.skill_probability:.2f} | {(rec.skill + ' (uncovered: ' + ', '.join(unc) + ')') if false_pos and unc else ('YES ' + rec.skill) if false_pos else 'no'} | - | {'yes' if fires else 'NO'} | {rec.topic} | {fmt(r_topic)} | {fmt(r_prompt)} | {fmt(r_tech)} | `{q_tech}` |")
        print(f"[remote]    {c['expect'][:40]:40s} local={rec.skill or 'none':16s} fp={false_pos} unc={unc} fired={fires} topic={fmt(r_topic)} prompt={fmt(r_prompt)} tech={fmt(r_tech)} q={q_tech!r}", flush=True)
    lines += ["", f"**Local suggestion made: {fp}/10 · skills.sh search fired (either path): {fired}/10 · Target found via topic query: {hit_topic}/10 · via prompt query: {hit_prompt}/10 · via tech query (now used by the hook): {hit_tech}/10**", ""]

    # ----------------------------------------------------------- session goals
    lines += ["## Session goals (v0.2 flow: one goal per session, `intent set`)", "",
              "| goal | expected | Jev top-1 | p | needs | outcome | verdict |", "|---|---|---|---|---|---|---|"]
    g_top1 = 0
    for c in CASES["session_goals"]:
        rec = route(build_state(c["goal"], cwd=CWD, goal=True), skills)
        lat.append(rec.latency_ms); tok.append(rec.usage.get("input_tokens") or 0)
        hit = rec.skill == c["expect"] and rec.outcome == "A"
        g_top1 += hit
        lines.append(f"| {c['goal'][:50]} | {c['expect']} | {rec.skill or 'none'} | {rec.skill_probability:.2f} | {rec.needs_skill:.2f} | {rec.outcome} | {'PASS' if hit else 'MISS'} |")
        print(f"[goal]      {c['expect']:18s} -> {rec.skill or 'none':18s} p={rec.skill_probability:.2f} outcome={rec.outcome} {'PASS' if hit else 'MISS'}", flush=True)
    g_b = g_c = 0
    for key, label, counter in (("session_goals_not_installed", "expect B", "b"), ("session_goals_no_skill", "expect C", "c")):
        for c in CASES[key]:
            rec = route(build_state(c["goal"], cwd=CWD, goal=True), skills)
            lat.append(rec.latency_ms); tok.append(rec.usage.get("input_tokens") or 0)
            ok = rec.outcome == c["expect_outcome"]
            if counter == "b": g_b += ok
            else: g_c += ok
            lines.append(f"| {c['goal'][:50]} | {label} | {rec.skill or 'none'} | {rec.skill_probability:.2f} | {rec.needs_skill:.2f} | {rec.outcome} | {'PASS' if ok else 'MISS'} |")
            print(f"[goal]      {label:18s} -> {rec.skill or 'none':18s} p={rec.skill_probability:.2f} outcome={rec.outcome} {'PASS' if ok else 'MISS'}", flush=True)
    lines += ["", f"**Installed goals top-1 with outcome A: {g_top1}/10 · Not-installed goals → outcome B: {g_b}/5 · No-skill goals → outcome C: {g_c}/3**", ""]

    # ------------------------------------------------------------------- bonus
    lines += ["## Bonus: ambiguous case (Jev picked skill-creator; its description covers 'run evals to test a skill', so this is arguably correct)", ""]
    for c in CASES["bonus_ambiguous_checks"]:
        rec = route(build_state(c["prompt"], cwd=CWD), skills)
        lines.append(f"- `{c['prompt'][:70]}…` → {rec.skill or 'none'} p={rec.skill_probability:.2f} needs={rec.needs_skill:.2f} spoke={'yes' if rec.should_suggest else 'no'}")

    lines += ["", "## Cost and speed", "", f"- Jev calls: {len(lat)} · latency median {statistics.median(lat):.0f} ms, max {max(lat)} ms", f"- input tokens mean {statistics.mean(tok):.0f} → about ${statistics.mean(tok) * 0.042 / 1e6:.5f} per prompt", ""]
    out = ROOT / f"report-{date.today()}.md"
    out.write_text("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
