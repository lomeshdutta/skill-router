# Security

## What this tool touches

- **Outbound:** `api.typesafe.ai` (your API key, the session goal or prompt, directory names and file-type counts), and `skills.sh` through `npx skills find` (a search string). Nothing else. `scripts/check_invariant` fails if any other host appears in `src/`.
- **Local reads:** SKILL.md files in your Claude Code skill directories, your Claude Code settings, and transcript excerpts (last three user messages) when used as a per-prompt hook.
- **Local writes:** `~/.cache/skill-router/` (decision log, session files, search cache). The API key is never written there.
- **Installs:** none. The tool prints `npx skills add ...` commands; it never runs them.

## Your API key

Put it in `.env` at the project root (gitignored) or the environment. Never paste it into an issue, a log excerpt, or a pull request. If you think a key leaked, revoke it at console.typesafe.ai first, then tell us.

## Reporting

Open a GitHub issue titled "security" with no secret material in it, or email the maintainer address in the repository profile. You will get a reply within a week.

## Third-party skills

Skill descriptions from your installed skills are sent to Jev as data. This tool treats skill files, search results, and transcript text as data, never as instructions. It does not execute anything from a skill.
