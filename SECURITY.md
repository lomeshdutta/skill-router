# Security

## What this tool touches

- **Outbound to `api.typesafe.ai`:** your API key; the session goal (or, in the opt-in per-prompt mode, the prompt plus up to three of your recent messages, 400 characters each); the project's directory *name* (not its full path); a count of files by extension; the current git branch name; the first 500 characters of the project's `CLAUDE.md` if one exists; and the names and descriptions of every installed skill. If any of that is sensitive in your project, do not use this tool there, or set `SKILL_ROUTER_DISABLE=1`.
- **Outbound to `skills.sh`:** a search string, via `npx skills find`. Nothing else leaves the machine; `scripts/check_invariant` fails if any other host appears in `src/`, but it checks hosts, not payloads. The payload is built in one place, `src/skill_router/context.py`.
- **Local reads:** SKILL.md files in your Claude Code skill directories, your Claude Code settings, and transcript excerpts (last three user messages) when used as a per-prompt hook.
- **Local writes:** `~/.cache/skill-router/` (decision log, session files, search cache). The API key is never written there.
- **Installs:** none. The tool prints `npx skills add ...` commands; it never runs them.

## Your API key

Put it in `.env` at the project root (gitignored) or the environment. Never paste it into an issue, a log excerpt, or a pull request. If you think a key leaked, revoke it at console.typesafe.ai first, then tell us.

## Reporting

Open a GitHub issue titled "security" with no secret material in it, or email the maintainer address in the repository profile. You will get a reply within a week.

## Third-party skills

Skill descriptions from your installed skills are sent to Jev as data. This tool treats skill files, search results, and transcript text as data, never as instructions. It does not execute anything from a skill.
