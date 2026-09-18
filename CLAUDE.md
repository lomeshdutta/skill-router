# skill-router

Predicts which Claude Code skill a prompt needs. One Jev (TypeSafe AI) call per prompt, wired in as a `UserPromptSubmit` hook.

- Python 3.12, `uv`. Run things with `uv run skill-router ...` or `uv run pytest`.
- All Jev questions and thresholds live in `src/skill_router/questions.py`. Edit there, nowhere else.
- No `TYPESAFE_API_KEY` → automatic MOCK mode (keyword overlap). Output is labelled `mock`.
- Decisions are appended to `~/.cache/skill-router/decisions.jsonl`; `skill-router log` reads it. That file is the eval set for tuning thresholds.
- Sandbox project: local git only, no remote.
