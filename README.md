# skill-router

[![ci](https://github.com/lomeshdutta/skill-router/actions/workflows/ci.yml/badge.svg)](https://github.com/lomeshdutta/skill-router/actions/workflows/ci.yml)

A small command-line tool for [Claude Code](https://claude.com/claude-code) that picks the right skill for your session.

## The problem

Claude Code lets you install *skills*: folders of instructions that teach it a specific job, such as writing cold emails, auditing a page for SEO, reviewing a diff, or building a PowerPoint deck. They come from the [skills.sh](https://skills.sh) directory, from plugins, and from Claude Code itself.

Once you have more than a dozen, two things go wrong:

1. You forget which ones you have, so you do the work without the skill that would have helped.
2. Claude does not reliably notice on its own that a skill applies to what you asked.

skill-router fixes that by checking your installed skills against what you are trying to do, once, at the start of each session.

## How it works

1. You start a Claude Code session in a project where skill-router is set up.
2. If your first message makes the goal clear, Claude works it out. If not, Claude asks one question: *"What are you trying to get done this session?"*
3. Claude runs `skill-router intent set "<your goal>"`.
4. The tool lists every skill installed on your machine and asks [Jev](https://typesafe.ai), a decision model from TypeSafe AI, to rank them against your goal. Jev is not a chat model. It returns a probability for each skill plus a confidence score, in under half a second, for a fraction of a cent.
5. You get one of three answers:
   - **Load this skill.** For example: `/cold-email (probability 1.00)`.
   - **Nothing you have installed fits.** Claude is told to search skills.sh for you using the [find-skills](https://skills.sh/vercel-labs/skills/find-skills) skill.
   - **No skill needed.** Plain help is fine for this.
6. After that, nothing runs for the rest of the session. If you change tasks, type `/intent <new goal>`.

A real example from the author's machine:

```
$ skill-router intent set "write the cold outreach sequence for our fintech prospects"
[skill-router] Session goal: write the cold outreach sequence for our fintech prospects
Jev: task kind `marketing_growth`, needs-a-skill 0.84.
Relevant installed skills for this session:
  /cold-email (probability 1.00) — Write B2B cold emails and follow-up sequences that get replies
Load /cold-email with the Skill tool when the work starts. Do not install anything.
```

## Install

You need Python 3.12, [uv](https://docs.astral.sh/uv/), and a TypeSafe API key from [console.typesafe.ai](https://console.typesafe.ai).

```bash
git clone https://github.com/lomeshdutta/skill-router
cd skill-router
uv sync
cp .env.example .env         # open .env and paste your TypeSafe key
```

Then register the hook that runs at session start. For one project, run this inside that project's folder:

```bash
uv run --project /path/to/skill-router skill-router install-hook --write
```

For every project, write it into your user-level settings instead:

```bash
uv run skill-router install-hook --settings ~/.claude/settings.json --write
```

Recommended: install find-skills so the "nothing installed fits" answer leads somewhere. If it is missing, skill-router says so at that point and shows this command instead of searching:

```bash
npx skills add vercel-labs/skills --skill find-skills -g
```

Start a new Claude Code session and you are done. Without an API key, everything still runs in a **mock mode** that matches keywords instead of asking Jev. Its output is labelled `mock`, and the tests use it, so you can try the tool before signing up for anything.

## Commands

| Command | What it does |
| --- | --- |
| `skill-router intent set "<goal>"` | Rank installed skills against a goal and record the answer for this session |
| `skill-router intent show` / `clear` | Look at or forget the recorded goal |
| `skill-router catalog` | List the skills it can see on your machine |
| `skill-router search <query>` | Search skills.sh from the command line |
| `skill-router log` | Recent decisions, from `~/.cache/skill-router/decisions.jsonl` |
| `skill-router install-hook` | Print or write the Claude Code hook configuration |
| `skill-router suggest "<prompt>"` | Rank skills for a single prompt instead of a session goal |

Environment switches: `SKILL_ROUTER_MOCK=1` forces mock mode, `SKILL_ROUTER_DISABLE=1` silences the hook, `SKILL_ROUTER_APP_SKILLS_DIR` points at the Claude desktop app's bundled skills if they are somewhere unusual (the macOS location is detected automatically).

## Where it looks for skills

| Scope | Location |
| --- | --- |
| Project | `<your project>/.claude/skills/*/SKILL.md` |
| User | `~/.claude/skills/*/SKILL.md` |
| Plugins | enabled plugins under `~/.claude/plugins/cache/` |
| Desktop app | skills bundled with the Claude desktop app (pptx, docx, xlsx, pdf, ...), macOS only so far |
| Built in | skills compiled into Claude Code (code-review, simplify, ...). These have no file on disk, so they are listed by hand in `src/skill_router/catalog.py` |

Skills you have switched off in Claude Code's settings are excluded.

## Does it pick the right skill?

`uv run python evals/run_eval.py` runs the cases in `evals/cases.json` against Jev and writes a report to `evals/reports/`. None of the test prompts name the skill they expect. Results from the [latest report](evals/reports/2026-09-17.md), on a machine with about 130 installed skills:

| Test | Result |
| --- | --- |
| Session goal, the right skill is installed: picked it | 9 of 10 |
| Session goal, the right skill is only on skills.sh: said so | 4 of 5 |
| Session goal, no skill would help: stayed quiet | 3 of 4 |
| Single prompt, the right skill is installed: picked it | 10 of 10 |

Reproducing these numbers needs a TypeSafe key and a similarly sized set of installed skills; mock mode runs the same harness but its scores are meaningless by design. The misses are kept in the report and explained there rather than tuned away. Every question Jev is asked, and every threshold, lives in one file: [`src/skill_router/questions.py`](src/skill_router/questions.py).

## Why a decision model instead of asking an LLM

Asking a chat model "which of these 130 skills fits?" means writing a prompt, getting text back, parsing it, and trusting whatever confidence it chose to write. Jev takes a list of options and returns a calibrated probability for each one in a single evaluation. It cannot produce a malformed answer, it reports when it is unsure, and it costs about two orders of magnitude less. A quick probe confirmed it matches meaning rather than words: a prompt full of a skill's trigger words about an unrelated topic scored 0.00, while a paraphrase sharing no words with the skill's description scored 0.92.

## What it deliberately does not do

- **Run on every prompt.** The first version did. It was accurate on tests and irritating in practice, because once a session was *about* skills it kept suggesting the skill-authoring skill. Per-prompt mode still exists as an opt-in: `skill-router install-hook --event UserPromptSubmit --write`.
- **Install anything.** It prints install commands and tells Claude to ask you first.
- **Bias the skills.sh search.** When nothing installed fits, it hands off to find-skills without suggesting candidates, so that skill's own quality filter does the work.
- **Phone home.** No server, no telemetry of its own. Your goal text and directory name go to TypeSafe's API; the search string goes to skills.sh via `npx skills`.
- **Support other agents yet.** The hook contract and skill locations are Claude Code's. Other agents are a possible later step, not a silent promise.

The full list with reasons is in [`SPEC.md`](SPEC.md).

## Contributing and security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup and how to add a test case (it also explains the maintainer files `CONTEXT.md`, `STATE.md` and `SPEC.md`), and [`SECURITY.md`](SECURITY.md) for what the tool sends where and how to report a problem. Licensed under MIT.
