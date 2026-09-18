<!-- loop-factory doctrine v0.4.1 · a change to the mechanic edits this file and a decision record in the same commit as the code -->
# skill-router — product spec

Status: draft

## What we are building

A small tool for Claude Code that answers one question at the start of a session: which of the skills you already installed should Claude load for what you are about to do? It asks Jev, a fast decision model from TypeSafe AI, to rank every installed skill against a one-sentence goal, tells you the answer once, and then gets out of the way. When nothing you have installed fits, it points Claude at the find-skills skill so the public skills.sh directory gets searched without our thumb on the scale.

## Who it is for, and who pays

User: a Claude Code user with more installed skills than they can keep in their head (the author has 131). Payer: the same person, through their own TypeSafe API key, at roughly $0.0004 per session. Nobody pays the project; what is being bought is the author's learning about decision models in agent tooling, and a credible first open-source release.

## The mechanic

1. A Claude Code session starts. A SessionStart hook tells Claude: infer the session goal from the first message, or if it is unclear, ask one question.
2. Claude runs `skill-router intent set "<goal>"`.
3. The tool builds a catalog of installed skills (project, user, plugin, app, built-in), sends the goal plus light session signals to Jev in one call, and reads back a probability for every skill, a confidence, and a "does a skill help at all" probability.
4. It reports one of three outcomes: relevant installed skills to load; nothing fits, use find-skills; or no skill needed.
5. Claude relays that to the user and proceeds. Nothing runs on later prompts. A pivot is the user typing `/intent <new goal>`.
6. Every decision is appended to a local log, which is the eval set for tuning thresholds.

## What we are NOT building

- Per-prompt routing — shipped as v0.1, dropped 2026-09-17: correct on the eval, noisy in real sessions (suggested `skill-creator` on 4 of 5 prompts once the session was about skills). Kept as an opt-in `skill-router hook` command, unregistered by default.
- Pre-seeding find-skills with our own skills.sh results — a candidate list anchors Claude's search and turns find-skills' quality filter into a rubber stamp.
- Installing skills automatically — every install is the user's explicit action; the tool prints commands, never runs `npx skills add`.
- A hosted service or shared catalog — the catalog is what is on your disk; no server, no telemetry.
- Support for agents other than Claude Code in v0.2 — the hook contract and skill locations are Claude Code's; other agents are a later decision record, not a silent widening.
- A loop-factory Tier 2 fleet — single-maintainer project; the cost of a wrong merge is minutes.
- Fine-tuning or custom Jev models — Jev is shaped through questions and state only; that is the whole point of the design.

## Riskiest assumption

Assumption: a one-sentence session goal carries enough signal for Jev to pick the right skill from ~130, at least as well as a single prompt did.
Tested by: the `session_goals` slice of `evals/run_eval.py` (G2).
Falsified if: top-1 accuracy on the 10 installed-skill goals is below 7/10, in which case the design falls back to routing the first *prompt* rather than a summarised goal.

## Freshness

- as-of 2026-09-17 · Proven · Jev endpoint `POST api.typesafe.ai/v1/systemone`, model `jev-1.13.0` behind `jev-latest`, $0.042/Mtok input, output free · basis: docs.typesafe.ai fetched and a live call.
- as-of 2026-09-17 · Proven · skills.sh HTTP API requires a Vercel OIDC token (401 without); `npx skills find` works anonymously · basis: fetch of /api/v1/skills → 401; CLI run.
- as-of 2026-09-17 · Proven · Claude Code SessionStart hooks can inject `additionalContext` but cannot ask the user a question · basis: code.claude.com/docs/en/hooks fetched.

## Success metric

Installed-skill top-1 accuracy on the eval, currently 10/10 for single prompts (Proven) and unmeasured for session goals (G2's job). Success for v0.2: ≥ 9/10 on session goals with zero suggestions on the five "no skill" goals.

## Gate S

Pending. Approving this spec approves: dropping per-prompt routing, the three-outcome session flow, the find-skills hand-off without pre-seeding, and the cut list above.
