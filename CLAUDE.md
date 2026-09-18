# skill-router

Predicts which Claude Code skill a session needs. One Jev (TypeSafe AI) call per session goal, wired in as a `SessionStart` hook plus `skill-router intent set`. Per-prompt routing is legacy and opt-in.

- Python 3.12, `uv`. Run things with `uv run skill-router ...` or `uv run pytest`.
- All Jev questions and thresholds live in `src/skill_router/questions.py`. Edit there, nowhere else.
- No `TYPESAFE_API_KEY` → automatic MOCK mode (keyword overlap). Output is labelled `mock`.
- Decisions are appended to `~/.cache/skill-router/decisions.jsonl`; `skill-router log` reads it. That file is the eval set for tuning thresholds.
- Ground truth for accuracy claims: `evals/cases.json` → `uv run python evals/run_eval.py` → `evals/reports/`.
- Open source (MIT) at github.com/lomeshdutta/skill-router; this repo is pinned to the lomeshdutta GitHub account. Keep absolute home-directory paths out of tracked files.

## Loop-engineering methodology (loop-factory v0.3)
- Read `CONTEXT.md` (binding terms + evidence rules) then `STATE.md` (live state; update before session end). `SPEC.md` holds the mechanic and, bindingly, what is NOT being built.
- Claims labeled Proven / Probable / Not Yet Claimed with basis; verified means verified by execution.
- Substantive commits carry Decision/Constraints/Rejected/Evidence/Rollback trailers (`githooks/commit-msg` warns when missing; docs-only commits exempt).
- Never-happens invariant: the tool never blocks or crashes a Claude Code session, the TypeSafe key is sent only to api.typesafe.ai, and nothing is installed without explicit user approval — enforced by `uv run pytest -q tests/test_invariant.py && scripts/check_invariant`.
- Every [H] gate ask includes a ~150-word understanding brief: the problem, why this design, rejected alternatives, impact.
