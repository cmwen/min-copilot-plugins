# knowledge-space-starter

`knowledge-space-starter` is a GitHub Copilot CLI plugin for building a reusable software-team workspace inside Copilot.

It bundles:

- role-based custom agents for common software-delivery work
- reusable skills for discovery, architecture decisions, and team handoffs
- a skill-forge workflow for turning solved conversations into reusable Copilot skills
- starter guidance you can extend later with more roles or domain-specific skills

## Files

```text
plugins/knowledge-space-starter/
├── plugin.json
├── agents/
│   ├── knowledge-space-architect.agent.md
│   ├── knowledge-space-engineer.agent.md
│   ├── knowledge-space-product-owner.agent.md
│   ├── knowledge-space-researcher.agent.md
│   └── knowledge-space-skill-forge.agent.md
├── scripts/
│   └── knowledge_space_skill_forge.py
├── skills/
│   ├── knowledge-space-architecture-decision/
│   │   └── SKILL.md
│   ├── knowledge-space-discovery/
│   │   └── SKILL.md
│   ├── knowledge-space-handoff/
│   │   └── SKILL.md
│   └── knowledge-space-skill-forge/
│       └── SKILL.md
└── tests/
    └── test_knowledge_space_skill_forge.py
```

## Included agents

- `knowledge-space-product-owner`
- `knowledge-space-researcher`
- `knowledge-space-architect`
- `knowledge-space-engineer`
- `knowledge-space-skill-forge`

## Local development

Install the plugin from this repository checkout:

```sh
copilot plugin install ./plugins/knowledge-space-starter
```

Because Copilot CLI caches installed plugin contents, reinstall the plugin after local edits:

```sh
copilot plugin install ./plugins/knowledge-space-starter
```

## Usage

Check that the plugin loaded:

```sh
copilot plugin list
```

List available skills:

```text
/skills list
```

Use a role directly:

```sh
copilot --agent knowledge-space-product-owner --prompt "Turn this product idea into a clear scope and acceptance criteria"
copilot --agent knowledge-space-architect --prompt "Propose a system design and tradeoff analysis for this feature"
copilot --agent knowledge-space-skill-forge --prompt "Convert this solved conversation into a reusable Copilot skill"
```

## Recommended workflow

Start with the product owner or researcher when the problem is still fuzzy.

Move to the architect once the constraints and desired outcomes are clear.

Hand the resulting brief to the engineer for implementation planning or code changes.

Use `knowledge-space-skill-forge` after a high-value problem is solved and you want to preserve the reusable pattern as a custom skill.

## Skill-forge setup

The included script can write or update a skill in a user-managed skills repository.

It looks for one of these environment variables:

- `COPILOT_CUSTOM_SKILLS_DIRS`: an `os.pathsep`-separated list of candidate directories
- `COPILOT_CUSTOM_SKILL_REPO`: a fallback repository root that contains a `skills/` directory

Each candidate may point either to the repository root or directly to the `skills/` directory.

Dry-run a generated skill spec:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json \
  --dry-run
```

Write the skill into your configured skills repository:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json
```

Commit after review:

```sh
python3 plugins/knowledge-space-starter/scripts/knowledge_space_skill_forge.py \
  --spec-file /tmp/skill-spec.json \
  --commit \
  --commit-message "Add reusable skill for dependency incident triage"
```

Add `--push` only after you have reviewed the diff and explicitly want the script to push the committed change.

Run the bundled tests with:

```sh
python3 -m unittest plugins/knowledge-space-starter/tests/test_knowledge_space_skill_forge.py
```
