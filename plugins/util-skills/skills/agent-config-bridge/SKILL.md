---
name: agent-config-bridge
description: Analyze a repository, plan safe config bridging between GitHub Copilot CLI and OpenCode, and apply the approved translation.
---

# Purpose

Use this skill when the user wants to understand or bridge agent-related repository configuration between GitHub Copilot CLI and OpenCode.
It inspects the current repository, inventories agent, skill, MCP, command, and instruction files, and then uses `plugins/util-skills/scripts/agent_config_bridge.py` to generate a transparent bridge plan.

The helper is **safety-first**:

- it uses `scan` and `plan` before `apply`
- it prefers relative symlinks where file formats are already compatible
- it generates wrapper files when schemas differ
- it refuses repo-escape paths and refuses to overwrite existing non-symlink files

# Determine the repository root first

Before running the helper, determine the repository root explicitly.
Use the user's requested directory when provided; otherwise inspect the current working tree and identify the top-level repository root before continuing.

All helper invocations should pass `--repo-root <repo-root>` so the scan, plan, and apply steps operate on the same tree.

# What can be symlinked directly

The bridge can safely create **relative symlinks** for assets that already share the same Markdown-based structure:

- Copilot skill `skills/<name>/SKILL.md` -> OpenCode `.opencode/skills/<name>/SKILL.md`
- OpenCode skill `.opencode/skills/<name>/SKILL.md` (or compatibility roots under `.claude/skills` and `.agents/skills`) -> Copilot `skills/<name>/SKILL.md`
- OpenCode commands -> Copilot skill-local `source-command.md` provenance files
- `.github/copilot-instructions.md` -> `AGENTS.md` only when targeting OpenCode and no `AGENTS.md` already exists

# What must be translated instead of symlinked

These assets require generated wrapper or config files instead of raw symlinks:

- Copilot custom agents `agents/*.agent.md` -> generated OpenCode `.opencode/agents/*.md`
- OpenCode agents `.opencode/agents/*.md` -> generated Copilot `agents/*.agent.md`
- Copilot `.mcp.json` -> generated OpenCode `opencode.json` `mcp` entries
- OpenCode `opencode.json` or `opencode.jsonc` `mcp` entries -> generated Copilot `.mcp.json`
- OpenCode commands `.opencode/commands/*.md` -> generated Copilot `skills/<name>/SKILL.md` wrappers plus symlinked source markdown

# Required workflow

## Step 1 — Scan

Run the helper in scan mode first:

```sh
python3 plugins/util-skills/scripts/agent_config_bridge.py scan \
  --repo-root <repo-root>
```

Review the structured inventory and identify whether the repository is classified as `copilot`, `opencode`, `mixed`, or `none`.

## Step 2 — Plan

Generate a plan before any writes or symlink creation:

```sh
python3 plugins/util-skills/scripts/agent_config_bridge.py plan \
  --repo-root <repo-root> \
  --target <copilot|opencode> \
  [--source-root <source-root>] \
  [--target-root <target-root>]
```

Always show the exact plan to the user.
The plan makes each operation explicit as `link`, `write-file`, `write-json`, or `skip`, with reasons.

## Step 3 — Ask for explicit yes/no approval

**Before running `apply`, present the exact plan and ask the user for explicit confirmation.**
Use a direct yes/no question such as:

> Shall I apply this exact bridge plan? (yes/no)

Do not create any files or symlinks until the user answers `yes`.

## Step 4 — Apply only the approved plan

After approval, run:

```sh
python3 plugins/util-skills/scripts/agent_config_bridge.py apply \
  --repo-root <repo-root> \
  --target <copilot|opencode> \
  [--source-root <source-root>] \
  [--target-root <target-root>]
```

## Step 5 — Report the result

Summarize:

- the repository classification
- the source root and target root used
- every planned `link`, `write-file`, `write-json`, and `skip`
- the final apply summary
- any collisions, skipped remote MCP entries, or ambiguous mixed-root cases

# Mixed repositories and collision risks

If the repository contains multiple possible Copilot plugin roots or multiple OpenCode-compatible skill roots, do **not** guess.
Surface the ambiguity in the plan and ask the user which source root should be used.

If a destination file already exists as a regular file, treat that as a collision risk.
Do not overwrite it silently.

If a destination symlink already points at the correct source, it is safe to keep it as-is.

# Output expectations

Return a concise summary with:

```
Classification: <copilot|opencode|mixed|none>
Target: <copilot|opencode>
Source root: <path>
Target root: <path>
Planned actions:
- <action> <destination> — <reason>
Apply summary:
- linked: <n>
- written: <n>
- json_written: <n>
- kept: <n>
- skipped: <n>
```

# Quality bar

- Determine the repository root first.
- Run `scan` or `plan` before `apply`.
- Never apply changes without explicit yes/no user confirmation.
- Prefer relative symlinks only when the formats are truly compatible.
- Generate transparent wrappers when schemas differ.
- Refuse risky guesses in mixed or ambiguous repositories.
