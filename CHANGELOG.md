# Changelog

## Unreleased

- Fix: `session-start` now honours `SKILL_ROUTER_DISABLE=1`.
- Fix: `intent set` no longer crashes when the session directory cannot be created; it prints the routing answer with a note.
- Fix: the eval harness skips session-goal cases whose skill is not installed on the machine, matching the single-prompt slice.
- Fix: the absolute project path is no longer sent to Jev; SECURITY.md lists every outbound field.
- Outcome B tells the user when the find-skills skill is missing.

## 0.2.0 — 2026-09-17

- Route once per session: a `SessionStart` hook asks Claude to establish the session goal (one question, only if unclear), then `skill-router intent set "<goal>"` reports one of three outcomes: installed skills to load, search skills.sh with the find-skills skill, or no skill needed.
- Per-prompt routing (`UserPromptSubmit` hook) is no longer registered by default. It remains available with `skill-router install-hook --event UserPromptSubmit`.
- Catalog now includes the desktop app's bundled skills (pptx, docx, xlsx, ...) and Claude Code's built-in skills (code-review, simplify, ...).
- Short skill descriptions are enriched from the skill body so Jev has something to match on.
- Eval harness with session-goal slices; report in `evals/reports/`.
- loop-factory Tier 1: secret-wall commit hook, `CONTEXT.md`, `STATE.md`, `SPEC.md`, `scripts/check_invariant`.

## 0.1.0 — 2026-09-17

- First prototype: per-prompt Jev routing over installed skills, mock mode, skills.sh fallback via `npx skills find`, decision log.
