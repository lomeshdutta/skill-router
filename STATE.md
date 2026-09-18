<!-- loop-factory doctrine v0.4.1 · maintained by the working agent: update before every session end -->
# State

Updated: 2026-09-17. Budget ceiling: Jev spend is negligible (~$0.0004/call); pause if a single eval run exceeds $1. Selftest gate: `uv run pytest -q && scripts/check_invariant`.

A fresh agent (or human) must be able to resume this project from this file alone. If it can't, this file is wrong — fix it first.

## Goals

| Goal | Status | Notes |
| --- | --- | --- |
| G1 Tier 1 scaffold | done | hooks installed + exercised (2 blocked leaks, 1 pass), CONTEXT/STATE/SPEC, check_invariant green, 18 tests |
| G2 session-intent redesign | done | SessionStart hook + `intent set`; per-prompt hook unregistered (opt-in); find-skills installed; session_goals eval 9/10 A, 4/5 B, 3/3 C |
| G3 open-source hygiene | done | MIT, CONTRIBUTING, SECURITY, CHANGELOG, CI workflow, ruff clean, portable paths, README rewritten; no home paths in tracked files |

<!-- Status vocabulary: pending / running / done / blocked (name the dependency) / decided: promote | park | kill. -->

## Approvals

- Gate S (spec): approved 2026-09-17 — via plan approval (three-outcome session flow, find-skills hand-off without pre-seeding, cut list).
- Gate P (publish): approved 2026-09-17 — github.com/lomeshdutta/skill-router, private first, public once CI is green; LICENSE and author "Lomesh Dutta"; history rewritten to that author before first push.

## Evidence ledger

| Claim | Grade | Basis |
| --- | --- | --- |
| Jev picks the right installed skill from 131 for a single prompt | Proven | evals/report-2026-09-17.md, installed slice top-1 10/10, real `jev-1.13.0` |
| Jev is semantic, not lexical | Proven | 6-probe test 2026-09-17: lexical decoys 0.00/0.49, zero-overlap paraphrase 0.92 |
| skills.sh target found for not-installed prompts | Proven | same report, tech-term query 9/10 (topic-only query 1/10) |
| Per-prompt routing is net useful in real sessions | Historical — v0.1 per-prompt hook | decision log 2026-09-17: skill-creator suggested on 4 of last 5 prompts once the session was about skills; replaced by session intent (G2) |
| A one-sentence session goal is enough for Jev to pick the right skill | Proven | evals/report-2026-09-17.md session_goals: 9/10 top-1 with outcome A (bar was 7/10); miss = firecrawl-scrape p=0.81 gated to C by needs_skill<0.50 |
| Not-installed goals fall through to find-skills (outcome B) | Proven | same report 4/5; the 1 = Remotion → installed `video` skill whose description lists Remotion |
| No-skill goals stay silent (outcome C) | Proven | same report 3/3 |
| Median Jev latency ~360 ms, ~9,100 input tokens, ~$0.0004/call | Probable | 38 calls on one machine, US West Coast (evals/reports/2026-09-17.md) |
| The eval harness runs without a key | Proven | `SKILL_ROUTER_MOCK=1 uv run python evals/run_eval.py --no-remote --cwd .` wrote a mock report (numbers meaningless by design) |

## Work log

- 2026-09-17 (night): G3 open-source hygiene landed; 19 tests, ruff, invariant, mock eval all green.
- 2026-09-17 (later): G1 scaffold and G2 session-intent landed; find-skills installed globally; 19 tests + invariant green.
- 2026-09-17: v0.1 built (per-prompt hook, catalog, mock mode, eval harness, 8 commits). Real Jev verified. Design decision to drop per-prompt routing. loop-factory Tier 1 retrofit started.

## Blockers / decisions needed

- Threshold tuning candidate: STRONG_PICK_MIN_PROB 0.85 vs firecrawl-scrape at 0.81/needs 0.4x → outcome C. Decide with more decision-log data, not one case.
