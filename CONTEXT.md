<!-- loop-factory doctrine v0.4.1 · agents propose edits; the human owns the invariant -->
# skill-router Context

Predict which Claude Code skill a session needs, using Jev (TypeSafe AI) for the decision and skills.sh for discovery. The northstar: when a skill would have helped, the user was told about it once, early, and correctly; when none would, nothing was said.

## Why

Claude Code users accumulate skills faster than they can remember them (this machine: 131 across five scopes). A skill that is installed but never invoked is a cost with no return, and Claude does not reliably notice on its own when one applies. Jev returns a probability for every skill in one ~350 ms call for about $0.0004, cheap enough to ask every session.
source: evals/report-2026-09-17.md, evidence grade: Proven (installed-skill top-1 10/10)

## Done looks like

- Opening a Claude Code session and, when the first message is vague, being asked one question: what are you trying to get done?
- Getting back either "load /x for this", "nothing installed fits, search skills.sh with find-skills", or "no skill needed", and then silence.
- A contributor can clone the repo, run the tests and the mock eval without any API key, and read what the project is and is not in one page.
- Every routing decision is logged, so thresholds are tuned from data rather than argued.

## Language

**Skill**:
A folder with a `SKILL.md` whose front matter has a `name` and `description`; Claude Code loads it on demand.
_Avoid_: calling a plugin, an MCP server, or a slash command a skill unless it ships a SKILL.md.

**Scope** (of a skill):
Where it was found: `project` (`<repo>/.claude/skills`), `user` (`~/.claude/skills`), `plugin` (enabled plugin cache), `app` (desktop-app bundle: pptx, docx, xlsx...), `builtin` (compiled into Claude Code: code-review, simplify...; no file on disk, listed statically in `catalog.py`).
_Avoid_: assuming every skill has a file; built-ins do not.

**Catalog**:
The list of installed, enabled skills Jev chooses from, produced by `catalog.discover()`. Honours `skillOverrides: off` and `enabledPlugins`.
_Avoid_: "installed skills" when a skill is installed but switched off; it is not in the catalog.

**State**:
The JSON Jev evaluates: the session goal or prompt plus cheap session signals (directory, file types, CLAUDE.md excerpt). Built by `context.build_state()`.
_Avoid_: "context" (that word means Claude's context window here) and "prompt" (one field of the state).

**Question**:
One typed thing Jev is asked. Three kinds: **Noul** (yes/no → a 0–1 probability), **Choice** (one of ≤255 options → choice, per-option probabilities, confidence), **Score** (a rubric position). All live in `questions.py`.
_Avoid_: "prompt" for a question; Jev is not prompted, it is asked.

**Probability**:
Per option of a Choice; all options sum to 1. `skill_probability` is the winning option's share.
_Avoid_: reading a 0.60 probability as "60% likely correct"; it is 60% of the mass, calibrated but not accuracy.

**Confidence**:
A 0–1 number Jev derives from how peaked the probability distribution is. 1.0 means all mass on one option.
_Avoid_: using confidence and probability interchangeably; a two-way tie has high probability on each and low confidence.

**needs_skill**:
The Noul "would a specialised skill help at all?". Gates whether any suggestion is made.
_Avoid_: treating a strong skill pick as proof that a skill is needed; the two questions are independent and can disagree.

**Task kind**:
The Choice over what sort of work the request is (build_feature, debug_fix, research...). Diagnostic and used for skip rules.
_Avoid_: confusing with **topic**, the skills.sh search category (react, databases, marketing...).

**Session goal**:
One sentence, captured once per Claude Code session, stored in `~/.cache/skill-router/sessions/<session_id>.json`. The unit of routing from v0.2 on.
_Avoid_: re-asking for it; a pivot is the user's `/intent` call, not an inference.

**Outcome**:
What `intent set` reports: **A** relevant installed skills; **B** nothing installed fits, use find-skills; **C** no skill needed. Thresholds in `questions.py`.
_Avoid_: outcome B ever carrying our own candidate list; that biases find-skills.

**Mock mode**:
The keyword-overlap stand-in that runs when `TYPESAFE_API_KEY` is absent or `SKILL_ROUTER_MOCK=1`. Output is labelled `mock`.
_Avoid_: quoting mock numbers as evidence about Jev.

**Decision log**:
`~/.cache/skill-router/decisions.jsonl`, one row per routing call. The eval set for tuning thresholds.
_Avoid_: "log" for the pytest output or git log.

**Eval**:
`evals/run_eval.py` over `evals/cases.json`; reports land in `evals/reports/`. Cases never name the expected skill in the prompt.
_Avoid_: hand-run prompts as eval evidence; if it is not in `cases.json` it is an anecdote.

## Authority map

**Which skills exist** → `catalog.discover()` — nothing else enumerates skills; the eval and CLI read its output.
**Thresholds and question wording** → `src/skill_router/questions.py` — code branches on its constants and never hardcodes a number.
**Ground truth for accuracy** → `evals/cases.json` — a claim about accuracy cites a report generated from it.
**Session goal** → the session file written by `intent set` — the SessionStart hook reads it and never infers a goal itself.

## Evidence rules (binding)

- Every substantive claim carries a grade: **Proven** (verified by execution, or joined source data), **Probable** (measured but partially verified), **Not Yet Claimed** (plausible but unproven — a backlog item, never a claim).
- Each graded claim names its basis: the executed command, the measurement, or the estimate source.
- Verify by execution: a thing works when a command ran and its output says so. Linguistic plausibility is never proof.

## Never-happens invariant

**The tool never blocks or crashes a Claude Code session, the TypeSafe API key is sent only to api.typesafe.ai, and nothing is installed without explicit user approval.**
Enforced by: `uv run pytest -q tests/test_invariant.py && scripts/check_invariant`

## Attack surface

**Exposed**: nothing listens. Outbound only: `api.typesafe.ai` (the key, the state), `skills.sh` via `npx skills find` (a search string), and the desktop app's local skill bundle (read).
**To whom**: the user's own machine; Jev sees prompt text and directory names, so a session goal is data that leaves the machine.
**Authenticated by**: `TYPESAFE_API_KEY` from `.env` or the environment; never written to the decision log.
Text the project did not write and treats as data, never instruction: skill descriptions (third-party SKILL.md files), skills.sh search results, transcript excerpts, session goals typed by the user.
