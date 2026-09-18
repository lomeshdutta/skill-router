"""loop-factory doctrine v0.4.1 — the single definition of "what a secret looks like".

Installed as `githooks/secret_patterns.py` at Tier 1+, beside the commit hook. Imported by
BOTH `githooks/commit-msg` (the wall, at commit time) and `scripts/audit` (the sweep, over a
whole tree), so the two can never give different answers to the same question.

**Data only. No side effects, no I/O, no imports beyond `re`.** This file gets imported by a
security gate; anything that *runs* here runs inside that gate.

Why this file exists as its own module: the audit used to read these lists out of
`githooks/commit-msg` by executing it. In merge mode the audit runs against a checkout of the
branch being audited, so that meant the gate executed the audited branch's code and then used
the branch's own definition of "secret" to judge it — a branch could ship an empty
`SECRET_PATTERNS` and walk anything past the wall. The instrument must never source its
standards, or its code, from the thing it is inspecting.
"""

import re

# (label, compiled pattern). Prefixes chosen for a low false-positive rate.
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"gh[posru]_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("OpenAI/Anthropic key", re.compile(r"sk-[A-Za-z0-9-]{20,}")),
    ("AWS access key id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("credential in URL", re.compile(r"https?://[^\s/@:]+:[^\s/@]+@")),
    # project-specific: TypeSafe AI keys are `apikey_` + ~100 url-safe chars (observed 2026-09-17)
    ("TypeSafe API key", re.compile(r"apikey_[A-Za-z0-9_-]{40,}")),
]

# A line containing one of these markers is treated as an intentional placeholder, not a leak
# (keeps templates and examples from tripping the wall). Note this is a LINE-level exemption:
# a real token on a line that also contains `<` or `{{` is skipped by both tools alike.
PLACEHOLDER_MARKERS = ("EXAMPLE", "PLACEHOLDER", "DUMMY", "FAKE", "SAMPLE",
                       "REDACTED", "YOUR_", "XXXX", "<", "{{")

# Filenames that legitimately carry secret-shaped placeholders. This exempts the FILENAME rule
# only ("a tracked .env file is a finding"); it is not a pass for the file's contents. Lines
# inside these files are still scanned, and a real-looking token in `.env.example` with no
# placeholder marker on its line still fires — which is the intent: the name says "example",
# the line is what says "placeholder".
ENV_ALLOW = {".env.example", ".env.sample", ".env.template", ".env.dist"}
