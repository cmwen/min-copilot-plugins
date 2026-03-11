---
name: knowledge-space-skill-forge
description: Convert a solved conversation into a reusable Copilot skill and optionally sync it into a user-managed skills repository.
---

# Purpose

Use this skill after a complex problem has been solved and the conversation produced a reusable approach that should become a durable Copilot skill.

# What to capture

- The recurring trigger or problem shape
- The prerequisites and constraints
- The reusable workflow
- The expected output format
- The quality bar and safety checks
- The approval points for risky or write actions

# Workflow

1. Review the conversation and identify the real reusable pattern rather than the one-off details.
2. Decide whether to create a new skill or update an existing one.
3. Produce a structured JSON spec for the skill.
4. Resolve the destination using:
   - `COPILOT_CUSTOM_SKILLS_DIRS` for one or more candidate paths
   - `COPILOT_CUSTOM_SKILL_REPO` as a fallback repository root
   - an explicit script override if the user provides one
5. Dry-run the helper script first when the resulting skill shape is still under review.
6. Write the skill, review the diff, and only then commit or push if the user explicitly approves.

# Helper script

Use the helper script bundled with this plugin:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json \
  --dry-run
```

Then write the skill for real:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json
```

Only after review, and only with explicit approval:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json \
  --commit \
  --push
```

# JSON spec shape

The helper script expects a JSON object like this:

```json
{
  "slug": "dependency-incident-triage",
  "name": "dependency-incident-triage",
  "description": "Capture the reusable workflow for debugging and stabilizing a failing dependency upgrade.",
  "purpose": "Use this skill when a dependency update causes test failures, build errors, or rollout risk.",
  "workflow": [
    "Restate the dependency change and the observed failure.",
    "Separate baseline behavior from newly introduced breakage.",
    "Find the smallest reproducible failure.",
    "Compare available fixes and pick the safest path.",
    "Define validation and rollback checks."
  ],
  "output_format": [
    {
      "heading": "Failure summary",
      "bullets": [
        "What changed",
        "What broke",
        "Current impact"
      ]
    },
    {
      "heading": "Recovery plan",
      "bullets": [
        "Immediate mitigation",
        "Proposed fix",
        "Validation steps"
      ]
    }
  ],
  "quality_bar": [
    "Prefer reversible fixes first.",
    "State unsupported assumptions explicitly."
  ],
  "examples": [
    "Stabilize a Python dependency bump that breaks a test suite.",
    "Capture the recurring rollout playbook for browser automation dependency upgrades."
  ]
}
```

# Output expectations

Before writing anything, summarize:

- the reusable pattern you found
- whether you plan to create or update a skill
- which directory the helper script will target
- whether the result still needs human review before commit or push

# Quality bar

- Optimize for future reuse, not historical narration.
- Prefer updating an existing skill when overlap is high.
- Never hide missing configuration or missing repository access.
- Never commit or push without explicit user approval.
