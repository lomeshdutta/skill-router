# Contributing

Thanks for looking. This is a small project; the bar is "works, tested, explained".

## Setup

```bash
uv sync --all-groups          # Python 3.12, installs typesafe-sdk, pytest, ruff
cp .env.example .env          # optional: add a TypeSafe key for real Jev calls
uv run pytest -q
uv run ruff check .
scripts/check_invariant
```

Without a key every command runs in **mock mode** (keyword overlap) and says so. Tests and CI run in mock mode; nothing here needs a key to be green.

## Layout

- `src/skill_router/questions.py` holds every Jev question and every threshold. If you are changing what Jev is asked or when the tool speaks, it is this file.
- `src/skill_router/catalog.py` finds installed skills. Built-in Claude Code skills have no file on disk; they are listed by hand at the top of this module. Add new ones there.
- `evals/cases.json` is the ground truth. A claim about accuracy cites a report in `evals/reports/` generated from it.

## Adding an eval case

Add an entry to the right slice in `evals/cases.json`. The prompt or goal must not name the expected skill. Run `uv run python evals/run_eval.py --no-remote` (mock) or with a key for real numbers, and include the relevant lines from the report in your PR.

## Commits

Short imperative subject. For changes that alter behaviour, the maintainer adds `Decision:` / `Constraints:` / `Rejected:` / `Evidence:` / `Rollback:` trailers in the body; contributors are welcome to but not required.

Optional: `git config core.hooksPath githooks` installs a local commit hook that blocks commits containing credential-shaped strings or a staged `.env`. It is opt-in and never runs on your machine unless you set it.

## Maintainer docs

`CONTEXT.md` (terms and evidence rules), `STATE.md` (where things stand), and `SPEC.md` (what this is and, bindingly, what it is not) follow the author's "loop-factory" working method for agent-maintained projects: claims carry an evidence grade, commits carry decision trailers, and the project names one invariant it enforces with a script. They are for whoever maintains the project and its coding agent; you do not need them to contribute a fix.
