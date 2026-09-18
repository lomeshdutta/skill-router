# skill-router

Tell Claude Code which of your installed skills a session needs. One question at the start, one fast decision, then silence.

**Problem.** Claude Code skills pile up (this machine has 131 across project, user, plugin, app and built-in scopes). A skill that is installed but never invoked is a cost with no return, and Claude does not reliably notice on its own when one applies.

**Approach.** Ask [Jev](https://typesafe.ai), TypeSafe AI's decision model, to rank every installed skill against a one-sentence session goal. Jev is not a chat model: you send it typed questions and it returns a probability for every option plus a confidence, in about 350 ms, for roughly $0.0004 per call. That is cheap and fast enough to run at the start of every session, and the numbers let the tool threshold on evidence instead of parsing prose.

```
session starts ─► hook tells Claude: infer the goal from the first message, or ask ONE question
              ─► Claude runs:  skill-router intent set "write outreach emails to fintech VPs"
              ─► Jev ranks all installed skills in one call
              ─► one of three answers, then nothing more this session:
                   A  Relevant installed skills: /cold-email (1.00). Load it when the work starts.
                   B  No installed skill fits. Use the find-skills skill to search skills.sh.
                   C  General assistance is fine; no skill needed.
pivot?        ─► you type  /intent <new goal>
```

## Install

```bash
git clone https://github.com/ninjacoder13/skill-router && cd skill-router
uv sync
cp .env.example .env            # paste your TypeSafe key (console.typesafe.ai)
uv run skill-router install-hook --write      # registers the SessionStart hook for this project
```

For every project, write the hook into your user settings instead:

```bash
uv run skill-router install-hook --settings ~/.claude/settings.json --write
```

Optional but recommended for outcome B: install the [find-skills](https://skills.sh/vercel-labs/skills/find-skills) skill so Claude can search skills.sh with a quality filter:

```bash
npx skills add vercel-labs/skills --skill find-skills -g
```

No key? Everything runs in a labelled **mock mode** (keyword overlap), including the tests and the eval.

## Commands

| Command | What it does |
| --- | --- |
| `skill-router intent set "<goal>"` | Route a session goal; prints outcome A, B or C and records it for the session |
| `skill-router intent show` / `clear` | Inspect or reset the recorded goal |
| `skill-router session-start` | The SessionStart hook (reads Claude Code's JSON on stdin) |
| `skill-router catalog` | List the installed skills Jev chooses from |
| `skill-router search <query>` | Search skills.sh via `npx skills find` |
| `skill-router log` | Recent decisions from `~/.cache/skill-router/decisions.jsonl` |
| `skill-router suggest "<prompt>"` / `hook` | Legacy per-prompt routing, opt-in (see below) |

Switches: `SKILL_ROUTER_MOCK=1` force mock mode, `SKILL_ROUTER_DISABLE=1` silence the hooks, `SKILL_ROUTER_APP_SKILLS_DIR` override where the desktop app's bundled skills live (macOS default is detected).

## How well does it work

`uv run python evals/run_eval.py` runs the cases in `evals/cases.json` against real Jev and writes `evals/reports/<date>.md`. On 2026-09-17, with 131 installed skills, none of the prompts naming the expected skill:

| Slice | Result |
| --- | --- |
| Session goals whose skill is installed: top-1 with outcome A | 9/10 |
| Session goals whose skill is only on skills.sh: outcome B | 4/5 |
| Session goals needing no skill: outcome C | 3/3 |
| Single prompts (legacy per-prompt mode): top-1 | 10/10 |

The one installed-goal miss was `firecrawl-scrape` picked at 0.81 but gated to "no skill" by a low needs-a-skill probability; a threshold question, tracked in `STATE.md`. The one outcome-B miss was a Remotion goal routed to an installed marketing `video` skill whose description explicitly lists Remotion, which is correct by that skill's own claim.

Every question Jev is asked and every threshold lives in [`src/skill_router/questions.py`](src/skill_router/questions.py). The decision log is the tuning set.

## What this is not

- **Not per-prompt.** Version 0.1 ran on every prompt. It scored 10/10 on the eval and was still noise in practice: once a session was *about* skills it suggested `skill-creator` on four prompts in a row. The per-prompt hook survives as an opt-in: `skill-router install-hook --event UserPromptSubmit --write`.
- **Not an installer.** It prints `npx skills add ...` commands and tells Claude to ask you; it never installs anything.
- **Not a search engine with a thumb on the scale.** When nothing installed fits, it hands off to find-skills without pre-seeding candidates, so that skill's own quality filter (install counts, source reputation) does the work.
- **Not a service.** The catalog is what is on your disk. No server, no telemetry beyond what `npx skills` itself sends (set `DISABLE_TELEMETRY=1` to stop that too).

See [`SPEC.md`](SPEC.md) for the full cut list with reasons.

## Why Jev rather than an LLM call

An LLM classifier would need a prompt, produce text, and require parsing; its "confidence" would be whatever it wrote. Jev returns a calibrated probability for each of up to 255 options in a single parallel evaluation, never produces a malformed answer, and costs two orders of magnitude less. A probe on this catalog confirmed it is matching meaning, not words: a prompt stuffed with a skill's trigger words about an unrelated topic scored 0.00; a paraphrase sharing no words with the description scored 0.92. Details in `evals/reports/`.

## Layout

```
src/skill_router/
  questions.py   every Jev question and threshold (start here)
  catalog.py     finds installed skills across five scopes; built-ins listed by hand
  context.py     builds the state Jev evaluates
  router.py      the Jev call, the mock, and the A/B/C outcome logic
  session.py     per-session goal file
  cli.py         all commands, including the two hooks
  skills_sh.py   `npx skills find` wrapper with a cache
  hook.py        legacy per-prompt hook
evals/           cases.json, run_eval.py, reports/
tests/           pytest, runs without a key
```

Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md). Security and key handling: [`SECURITY.md`](SECURITY.md). License: MIT.
