# skill-router

**Problem.** Claude Code sessions have dozens (here: ~200) of installed skills, and it is on you to remember which one to invoke. **Idea.** Every time you submit a prompt, ask Jev, TypeSafe AI's ~100 ms "decision model", which installed skill fits, and whisper the answer to Claude before it starts working.

```
you type a prompt
      │
      ▼  UserPromptSubmit hook (Claude Code runs it before the model sees the prompt)
skill-router hook
      │  builds a small `state`: prompt + cwd + file types + last 3 prompts
      ▼
Jev  (one HTTPS call, 4 questions answered in parallel)
      │  needs_skill?  task_kind?  which installed skill?  which skills.sh topic?
      ▼
"Suggested skill: /cold-email (p=0.81, confidence 0.72)"   ← injected into Claude's context
"No local fit → skills.sh: coreyhaines31/marketingskills@seo-audit"  ← only when nothing is installed
```

## Why Jev rather than another LLM call

- **Typed answers, not text.** Jev returns a probability for *every* installed skill (a `Choice` over up to 255 options) plus a `confidence`. The hook thresholds on those numbers instead of parsing prose.
- **Fast and cheap.** ~100 ms per call, $0.042 per million input tokens. One prompt costs roughly $0.0005 with ~100 skills in the catalog. That is cheap enough to run on every prompt.
- **Calibrated "I don't know".** Low confidence → the hook stays quiet or lists a few candidates instead of guessing.

## Setup

```bash
uv sync                                   # installs typesafe-sdk + dev deps
cp .env.example .env                      # then paste your key from https://console.typesafe.ai
export TYPESAFE_API_KEY=...               # the hook reads the environment Claude Code runs in
uv run skill-router suggest "audit the SEO of my landing page"
```

Without a key the router runs in **mock mode** (keyword overlap) so every command still works; output is labelled `mock`.

### Wire the hook into Claude Code

The project-local [.claude/settings.json](.claude/settings.json) already registers the hook for sessions started in this folder. For every project, add the same block to `~/.claude/settings.json`:

```bash
uv run skill-router install-hook --settings ~/.claude/settings.json          # prints the JSON
uv run skill-router install-hook --settings ~/.claude/settings.json --write  # merges it in
```

## Commands

| Command | What it does |
| --- | --- |
| `skill-router suggest <prompt>` | Classify one prompt; `--json` dumps state + probabilities |
| `skill-router catalog` | List the installed skills Jev chooses from (project, user, enabled plugins) |
| `skill-router search <query>` | Search skills.sh via `npx skills find` |
| `skill-router hook` | Hook entry point; reads Claude Code's JSON on stdin |
| `skill-router log` | Recent decisions from `~/.cache/skill-router/decisions.jsonl` |
| `skill-router install-hook` | Print or write the hook config |

Env switches: `SKILL_ROUTER_DISABLE=1` (off), `SKILL_ROUTER_MOCK=1` (force mock), `SKILL_ROUTER_QUIET=1` (hide the one-line hint shown to you).

## Where to tune

Everything Jev is asked, and every threshold, is in [src/skill_router/questions.py](src/skill_router/questions.py). Start there. The decision log is your eval set: run for a week, then adjust `SUGGEST_MIN_CONFIDENCE` and friends against real prompts.

## Layout

```
src/skill_router/
  questions.py   the 4 Jev questions + thresholds (review this file)
  catalog.py     finds installed SKILL.md files, honours skillOverrides / enabledPlugins
  context.py     builds the `state` (prompt, cwd signals, recent prompts)
  router.py      Jev call → Recommendation; mock fallback
  skills_sh.py   `npx skills find` wrapper with a 24 h cache
  hook.py        UserPromptSubmit glue; never blocks, never raises
  cli.py         argparse commands
tests/           offline tests (mock mode)
```

## Eval

`uv run python evals/run_eval.py` runs 20 prompts (10 installed skills, 10 that only exist on skills.sh) against real Jev and writes `evals/report-<date>.md`. Results on 2026-09-17:

| Slice | Result |
| --- | --- |
| Installed skills, top-1 | 10/10 |
| Installed skills, hook spoke with the right skill | 10/10 |
| Installed skills, unwanted extra skills.sh search | 0/10 |
| Not installed, skills.sh search fired | 8/10 |
| Not installed, target found on skills.sh | 9/10 with the tech-term query, up from 1/10 with a topic-only query |

The two not-installed cases where no search fires are Remotion and AI-video prompts: the installed marketing `video` skill's description explicitly lists Remotion and AI video, so Jev choosing it is correct by the skill's own claim.

### Two search paths
1. **No local fit** (Jev's pick is `none` or weak): search skills.sh with technology terms pulled from the prompt plus Jev's topic.
2. **Local fit but uncovered technology**: a skill was suggested, Jev says the prompt names a specific third-party technology, and the picked skill's description never mentions it. The hook shows the local suggestion *and* the skills.sh candidates, with a caveat. Skipped for research/planning/docs prompts where the technology is the subject, not the tool.

## Status

- Proven (executed 2026-09-17, 8 prompts, real key): Jev picked `cold-email`, `last30days`, and an SEO audit skill correctly, and answered "none" for a time-zone question, a test fix, and a database choice. Median latency 462 ms, ~7,100 input tokens, about $0.0003 per prompt.
- Proven: catalog discovery across project, user, plugin, desktop-app, and built-in scopes; hook JSON contract; skills.sh search.
- Probable: thresholds. They were set by judgment, not tuned. Use `skill-router log` after a week of real prompts.
