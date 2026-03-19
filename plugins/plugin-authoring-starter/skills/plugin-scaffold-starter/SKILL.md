---
name: plugin-scaffold-starter
description: Create a new GitHub Copilot CLI plugin skeleton with a manifest, starter documentation, agent files, skill directories, and optional MCP wiring.
---

# Purpose

Use this skill when the user wants to create a new Copilot CLI plugin or turn an ad hoc customization idea into a reusable plugin package.

# Required workflow

1. Identify the plugin's core workflow, intended audience, and preferred plugin name.
2. Create a plugin directory under `plugins/<plugin-name>/`.
3. Add a `plugin.json` manifest with:
   - `name`
   - `description`
   - `version`
   - `keywords`
   - `agents` when custom agents are included
   - `skills` when reusable skills are included
   - `mcpServers` when MCP config is included
4. Add the baseline file tree needed by the requested workflow:
   - `README.md`
   - `agents/*.agent.md`
   - `skills/<skill-name>/SKILL.md`
   - `.mcp.json` when external tooling is required
5. Keep naming consistent so the manifest and file layout resolve correctly.
6. Add local install and reload instructions using `copilot plugin install ./plugins/<plugin-name>`.

# Output expectations

Before writing files, summarize:

- the plugin name
- the intended directory tree
- which components will be bundled
- whether the plugin is for direct install only or marketplace publication

After writing files, summarize:

- which files were created
- how the manifest maps to the file tree
- what the first agent or skill is meant to do

# Quality bar

- Keep the plugin narrow and reusable.
- Prefer clear starter content over placeholder prose.
- Do not omit manifest fields that the file layout depends on.
- Do not claim MCP support unless the plugin actually includes and documents the MCP configuration.
