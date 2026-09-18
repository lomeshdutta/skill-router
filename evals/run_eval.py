"""Eval harness for skill-router. Usage: uv run python evals/run_eval.py [--no-remote] [--cwd DIR]

--no-remote  skip the skills.sh lookups (fast; what CI runs)
--cwd DIR    the project directory whose skills form the catalog (default: this repo's root)

Runs against real Jev when TYPESAFE_API_KEY is set, otherwise in labelled mock mode. Writes
evals/reports/<date>.md (or <date>-mock.md). Slices:

  installed                    single prompts whose skill is installed (legacy per-prompt mode)
  not_installed                single prompts whose skill only exists on skills.sh
  session_goals                one-sentence goals whose skill is installed (v0.2 flow)
  session_goals_not_installed  goals that should fall through to find-skills (outcome B)
  session_goals_no_skill       goals that need no skill (outcome C)
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from skill_router import catalog, skills_sh  # noqa: E402
from skill_router.context import build_state  # noqa: E402
from skill_router.router import Recommendation, route, use_mock  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
CASES = json.loads((ROOT / "cases.json").read_text())
REMOTE = "--no-remote" not in sys.argv
CWD = sys.argv[sys.argv.index("--cwd") + 1] if "--cwd" in sys.argv else str(ROOT.parent)


class Report:
    def __init__(self, n_skills: int) -> None:
        mode = "MOCK (keyword overlap, no API key)" if use_mock() else "real Jev"
        self.lines = [
            f"# skill-router eval, {date.today()}",
            "",
            f"Catalog: {n_skills} skills from `{CWD}`. Model: {mode}.",
            "",
        ]
        self.latency: list[int] = []
        self.tokens: list[int] = []

    def record(self, rec: Recommendation) -> None:
        self.latency.append(rec.latency_ms)
        self.tokens.append(rec.usage.get("input_tokens") or 0)

    def section(self, title: str, header: list[str]) -> None:
        self.lines += ["", f"## {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]

    def row(self, *cells: object) -> None:
        self.lines.append("| " + " | ".join(str(c) for c in cells) + " |")

    def summary(self, text: str) -> None:
        self.lines += ["", f"**{text}**"]

    def write(self) -> Path:
        REPORTS.mkdir(exist_ok=True)
        if self.latency:
            self.lines += [
                "",
                "## Cost and speed",
                "",
                f"- calls: {len(self.latency)} · latency median {statistics.median(self.latency):.0f} ms, max {max(self.latency)} ms",
                f"- input tokens mean {statistics.mean(self.tokens):.0f} → about ${statistics.mean(self.tokens) * 0.042 / 1e6:.5f} per call",
            ]
        out = REPORTS / (f"{date.today()}-mock.md" if use_mock() else f"{date.today()}.md")
        out.write_text("\n".join(self.lines) + "\n")
        return out


def remote_rank(expect: str, results: list[skills_sh.RemoteSkill]) -> str:
    """'#n' when the exact skill is at rank n, 'repo #n' when only its repo is, '-' when absent."""
    pkg, _, skill = expect.partition("@")
    for i, r in enumerate(results, 1):
        if r.package == pkg and r.skill == skill:
            return f"#{i}"
    for i, r in enumerate(results, 1):
        if r.package == pkg:
            return f"repo #{i}"
    return "-"


def log(label: str, expect: str, rec: Recommendation, verdict: str, extra: str = "") -> None:
    print(
        f"[{label:9s}] {expect[:40]:40s} -> {rec.skill or 'none':18s} p={rec.skill_probability:.2f} {verdict} {extra}",
        flush=True,
    )


def eval_installed(report: Report, skills: list[catalog.SkillInfo]) -> None:
    names = {s.name for s in skills}
    report.section(
        "Installed skills, single prompts (legacy per-prompt mode)",
        ["expected", "Jev top-1", "p", "conf", "needs", "spoke?", "top-3", "verdict"],
    )
    top1 = spoke = total = 0
    for c in CASES["installed"]:
        if c["expect"] not in names:
            print(f"[installed] {c['expect']:18s} skipped: not in this machine's catalog", flush=True)
            continue
        total += 1
        rec = route(build_state(c["prompt"], cwd=CWD), skills)
        report.record(rec)
        ranked = list(rec.skill_probabilities)[:3]
        hit = rec.skill == c["expect"]
        top1 += hit
        spoke += rec.should_suggest and hit
        verdict = "PASS" if rec.should_suggest and hit else ("top-3" if c["expect"] in ranked else "MISS")
        report.row(
            c["expect"],
            rec.skill or "none",
            f"{rec.skill_probability:.2f}",
            f"{rec.skill_confidence:.2f}",
            f"{rec.needs_skill:.2f}",
            "yes" if rec.should_suggest else "no",
            ", ".join(ranked),
            verdict,
        )
        log("installed", c["expect"], rec, verdict)
    report.summary(f"Top-1: {top1}/{total} · Hook spoke with the right skill: {spoke}/{total}")


def eval_not_installed(report: Report, skills: list[catalog.SkillInfo]) -> None:
    report.section(
        "Not installed, single prompts: should fall through to skills.sh",
        [
            "expected on skills.sh",
            "local pick",
            "p",
            "local suggest?",
            "search fired?",
            "topic",
            "rank via tech query",
            "query",
        ],
    )
    suggested = fired = found = 0
    for c in CASES["not_installed"]:
        rec = route(build_state(c["prompt"], cwd=CWD), skills)
        report.record(rec)
        query = skills_sh.build_query(c["prompt"], rec.topic, rec.task_kind)
        rank = remote_rank(c["expect"], skills_sh.find(query, limit=5)) if REMOTE else "(skipped)"
        suggested += rec.should_suggest
        fired += rec.should_search_skills_sh
        found += rank not in ("-", "(skipped)")
        report.row(
            c["expect"],
            rec.skill or "none",
            f"{rec.skill_probability:.2f}",
            "YES" if rec.should_suggest else "no",
            "yes" if rec.should_search_skills_sh else "NO",
            rec.topic,
            rank,
            f"`{query}`",
        )
        log("remote", c["expect"], rec, "fired" if rec.should_search_skills_sh else "local", f"rank={rank}")
    n = len(CASES["not_installed"])
    report.summary(
        f"Local suggestion made: {suggested}/{n} · search fired: {fired}/{n} · target found via tech query: {found}/{n}"
        + ("" if REMOTE else " (remote skipped)")
    )


def eval_session_goals(report: Report, skills: list[catalog.SkillInfo]) -> None:
    report.section(
        "Session goals (v0.2 flow: one goal per session, `intent set`)",
        ["goal", "expected", "Jev top-1", "p", "needs", "outcome", "verdict"],
    )
    hits = {"A": 0, "B": 0, "C": 0}
    totals = {"A": 0, "B": 0, "C": 0}
    slices = [("session_goals", "A"), ("session_goals_not_installed", "B"), ("session_goals_no_skill", "C")]
    for key, expected_outcome in slices:
        for c in CASES[key]:
            rec = route(build_state(c["goal"], cwd=CWD, goal=True), skills)
            report.record(rec)
            expect_skill = c.get("expect")
            ok = rec.outcome == expected_outcome and (expect_skill is None or rec.skill == expect_skill)
            totals[expected_outcome] += 1
            hits[expected_outcome] += ok
            report.row(
                c["goal"][:50],
                expect_skill or f"outcome {expected_outcome}",
                rec.skill or "none",
                f"{rec.skill_probability:.2f}",
                f"{rec.needs_skill:.2f}",
                rec.outcome,
                "PASS" if ok else "MISS",
            )
            log(
                "goal",
                expect_skill or f"outcome {expected_outcome}",
                rec,
                "PASS" if ok else "MISS",
                f"outcome={rec.outcome}",
            )
    report.summary(
        f"Installed goals → outcome A with the right skill: {hits['A']}/{totals['A']} · not-installed goals → B: {hits['B']}/{totals['B']} · no-skill goals → C: {hits['C']}/{totals['C']}"
    )


def main() -> None:
    skills = catalog.discover(CWD)
    report = Report(len(skills))
    eval_installed(report, skills)
    eval_not_installed(report, skills)
    eval_session_goals(report, skills)
    print(f"\nwrote {report.write()}")


if __name__ == "__main__":
    main()
