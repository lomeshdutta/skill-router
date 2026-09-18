"""Every Jev question and every threshold lives in this one file.

TypeSafe's own guidance: humans should review the *questions* and the *thresholds*,
so keep them together and out of the plumbing code.

Vocabulary
----------
- Noul   : a yes/no question. Jev returns a probability that the answer is "yes" (0..1).
- Choice : pick one option from a fixed list. Jev returns the winner, a probability for
           every option (they sum to 1), and a `confidence` (0..1) describing how peaked
           that distribution is.
- state  : the thing Jev evaluates. Here: the user's prompt plus session context.
"""

from __future__ import annotations

from typesafe_sdk import Choice, Noul

from skill_router.catalog import SkillInfo

# --------------------------------------------------------------------------- thresholds
# Confidence at or above which we recommend ONE skill outright.
SUGGEST_MIN_CONFIDENCE = 0.45
# A skill whose probability is at or above this is worth mentioning as a runner-up.
RUNNER_UP_MIN_PROB = 0.12
# Below this needs_skill probability we stay silent: plain coding help is fine...
NEEDS_SKILL_MIN = 0.50
# ...unless Jev is this sure about ONE specific skill. Observed 2026-09-17: `code-review` at
# p=1.00 and `xlsx` at p=0.97 arrived with needs_skill of only 0.37 / 0.34. A near-certain
# pick is better evidence than the generic "does this need a skill?" question.
STRONG_PICK_MIN_PROB = 0.85
# Search skills.sh only when the prompt clearly wants a skill but nothing local fits well.
SEARCH_SKILLS_SH_MIN_NEEDS = 0.60
SEARCH_SKILLS_SH_MAX_LOCAL_PROB = 0.40
# Jev supports up to 255 options in a Choice. Leave headroom for the "none" option.
MAX_SKILL_OPTIONS = 250
# Truncate skill descriptions sent to Jev (token cost is per input token).
MAX_DESCRIPTION_CHARS = 220

NONE_OPTION = "none"

# --------------------------------------------------------------------------- questions
NEEDS_SKILL = Noul(
    instructions=(
        "Would this request be handled noticeably better by following a specialized "
        "skill (a playbook, checklist, domain guide, or tool-specific procedure) than by "
        "general coding-assistant knowledge alone?"
    ),
    criteria={
        "true": (
            "The task is domain-specific (marketing, SEO, design, research, deployment, "
            "a particular framework or vendor) or follows a repeatable procedure where a "
            "written playbook would change the output."
        ),
        "false": (
            "A quick factual question, a small generic code edit, a clarification, "
            "casual conversation, or a task any competent engineer handles without a guide."
        ),
    },
)

TASK_KIND = Choice(
    instructions="What kind of work is the user asking for in this prompt?",
    criteria={
        "build_feature": "Write new code or add functionality to a project",
        "debug_fix": "Find and fix a bug, error, crash, or regression",
        "review_code": "Review, critique, or audit existing code or a diff",
        "test": "Write or run tests, QA, or verification",
        "refactor_simplify": "Restructure or clean up code without changing behavior",
        "devops_deploy": "Infra, CI/CD, deployment, servers, cron, environment setup",
        "data_analysis": "Analyze data, metrics, spreadsheets, or produce charts",
        "docs_writing": "Write or edit documentation, README, prose, or explanations",
        "marketing_growth": "Marketing, growth, SEO, copywriting, emails, launches, pricing",
        "research": "Research a topic, compare tools, gather sources, summarize the web",
        "design_ui": "Visual or UI/UX design, mockups, layouts, styling",
        "planning_strategy": "Plan, scope, decide between options, product or business strategy",
        "project_setup": "Scaffold a project, configure tooling, install dependencies",
        "conversation_other": "Chit-chat, meta questions about the assistant, or none of the above",
    },
)

# Categories used to search skills.sh when nothing installed fits.
# Mirrors skills.sh/topic plus a few broad buckets.
SKILLS_SH_TOPIC = Choice(
    instructions=(
        "If we searched a public library of AI-agent skills for help with this prompt, "
        "which topic would we search under?"
    ),
    criteria={
        "react": "React front-end work",
        "nextjs": "Next.js apps",
        "typescript": "TypeScript or Node.js beyond React",
        "python": "Python code, scripts, packaging, notebooks",
        "mobile": "iOS, Android, React Native, Expo",
        "design": "UI/UX, visual design, design systems",
        "databases": "SQL, Postgres, Prisma, Supabase, data modeling",
        "testing": "Unit/integration/e2e testing, QA",
        "devops": "Docker, CI/CD, cloud, deployment, servers",
        "security": "Security review, secrets, auth, vulnerabilities",
        "agent-workflows": "Building AI agents, prompts, MCP, skills, LLM apps",
        "marketing": "Marketing, growth, SEO, copywriting, sales",
        "writing": "Documentation, articles, editing, prose",
        "research": "Web research, literature review, competitive intel",
        "data": "Data analysis, spreadsheets, charts, ML",
        "video-media": "Video, image, audio generation or editing",
        "productivity": "Notes, planning, project management, calendars",
        NONE_OPTION: "No public skill category would help",
    },
)


def build_installed_skill_choice(skills: list[SkillInfo]) -> Choice:
    """One Choice over every installed skill, plus a 'none' escape hatch."""
    criteria: dict[str, str | None] = {}
    for s in skills[:MAX_SKILL_OPTIONS]:
        desc = (s.description or "").strip().replace("\n", " ")
        if len(desc) > MAX_DESCRIPTION_CHARS:
            desc = desc[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
        criteria[s.name] = desc or None
    criteria[NONE_OPTION] = (
        "No installed skill is a good fit; general assistance without a skill is best."
    )
    return Choice(
        instructions=(
            "Which installed skill should the coding assistant load to handle this prompt? "
            "Pick the skill whose description best matches what the user is trying to do. "
            "Pick 'none' if no skill clearly applies."
        ),
        criteria=criteria,
    )
