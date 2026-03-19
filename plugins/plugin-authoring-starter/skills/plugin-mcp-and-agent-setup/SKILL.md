---
name: plugin-mcp-and-agent-setup
description: Add custom agents, reusable skills, and MCP configuration to a Copilot CLI plugin while keeping the manifest and documentation aligned.
---

# Purpose

Use this skill when a plugin needs to grow beyond a bare manifest and bundle the reusable components that make it valuable: agent roles, skill workflows, and MCP server definitions.

# Required workflow

1. Determine which responsibilities belong in:
   - a custom agent
   - a reusable skill
   - an MCP server integration
2. For each custom agent:
   - create `agents/<agent-name>.agent.md`
   - set a unique `name`
   - describe when the agent should use one of the bundled skills
3. For each skill:
   - create `skills/<skill-name>/SKILL.md`
   - keep the skill `name` unique
   - define trigger, workflow, output expectations, and quality bar
4. For MCP:
   - add or update `.mcp.json`
   - point `plugin.json` at the MCP config using `mcpServers`
   - choose explicit server names and commands
   - document required runtime support
5. Re-check `plugin.json` so `agents`, `skills`, and `mcpServers` all match the actual file layout.

# Output expectations

Summarize:

- which agents were added and their roles
- which skills were added and when to invoke them
- which MCP servers were configured and why
- any runtime prerequisites or user-visible limitations

# Quality bar

- Keep agent IDs, skill names, and MCP server names collision-resistant.
- Never store secrets in the repository.
- Do not silently ignore missing runtime support; document it.
- Keep the README in sync with the manifest and bundled components.
