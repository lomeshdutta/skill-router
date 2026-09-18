# External review, 2026-09-18 (ChatGPT, independent environment)

A third party ran the repo on their own machine with a real TypeSafe key and reported the findings below. Their raw numbers are reproduced as given; the "Resolution" column is ours.

## Bugs reported

| Bug | Their reproduction | Resolution |
| --- | --- | --- |
| `SKILL_ROUTER_DISABLE=1` ignored by `session-start` | set the variable, pipe valid JSON, hook still emits routing instructions | Confirmed locally. Fixed: `session-start` now returns 0 with no output when disabled. Regression test `test_session_start_honours_disable`. |
| Session storage failure crashes `intent set` | put a regular file where the sessions directory's parent should be | Confirmed locally (`NotADirectoryError`). Fixed: the save is wrapped; the routing answer is still printed with a one-line note, exit 0. Regression test `test_intent_survives_unwritable_session_dir`. |

Both bugs sat outside the invariant script's reach: it asserts the entry points catch exceptions, and they did, but the disable check was simply missing and the save happened after routing in code the script does not inspect. The tests are the enforcement now.

## Harness defect reported

The single-prompt "installed" slice skipped skills not present in the reviewer's catalog; the session-goal slice did not, so nine goals whose skills were not installed on their machine counted as misses (1/10). Confirmed and fixed: both slices skip absent skills and the summary line says how many were skipped.

Two of the "routing misses" they listed follow from this defect rather than from Jev: an A/B-testing goal routed to `design` and a launch-readiness goal to `code-review` on a machine where `ab-testing` and `cto` were not installed. Jev picked the nearest installed skill, which is what it is asked to do.

## Their live results (30 Jev calls, jev-1.13.0, their catalog)

| Slice | Result |
| --- | --- |
| Code-review selection, prompt + goal | 2/2 |
| Missing-skill goals → search | 5/5 |
| No-skill goals → no recommendation | 3/4 |
| Missing-skill single prompts → search | 7/10 |
| Discovery searches (`npx skills find` directly) | 5/5 expected skill ranked first |
| Latency | median 4.96 s, max 8.43 s |

Remaining misses they flagged, with our reading:

- Remotion video prompt → `dataviz`; shadcn table prompt → `dataviz`. Nearest-installed-skill picks on their catalog. Same failure class we documented in `2026-09-17.md` (Remotion → `video` here). A dedicated skill on skills.sh would rank higher, but Jev only sees what is installed; this is the known cost of not searching skills.sh when a weak local match exists.
- Vercel-specific React review → `code-review`. Arguably useful; fails the benchmark's expected "search" outcome. Same as our finding.
- "Open-source this repo and publish eval results" → search. Same known miss as in our report (kept deliberately).

Latency: their median of ~5 s is more than ten times ours (~0.35 s, US West Coast). Location or network; we have no measurement from their environment beyond this figure. Worth noting in the README as a range rather than a single number.

## What this review did not test

The router's own search wrapper and the automatic Claude Code hand-off to find-skills; their five discovery searches called `npx skills find` directly.
