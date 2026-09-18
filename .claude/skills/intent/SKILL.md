---
name: intent
description: Set or change this session's goal and get skill-router's routing decision. Use when the user runs /intent <goal>, says "I'm switching to X now", "new task", or pivots to unrelated work mid-session.
---
# intent

Run, from the repository root (the command is installed in the project's virtualenv):

```bash
uv run skill-router intent set "$ARGUMENTS"
```

Relay its output to the user verbatim in substance: which installed skills to load, or that skills.sh should be searched with the find-skills skill, or that no skill is needed. If it names a skill, load that skill with the Skill tool before starting the work. Never install a skill without the user's explicit yes.

If `$ARGUMENTS` is empty, ask one question: "What are you trying to get done this session?" and run the command with the answer.
