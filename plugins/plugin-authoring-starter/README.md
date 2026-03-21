# plugin-authoring-starter

`plugin-authoring-starter` is a GitHub Copilot CLI plugin for creating new Copilot CLI plugins that bundle custom agents, reusable skills, marketplace metadata, and MCP configuration.

It bundles:

- a plugin-architecture agent for defining the plugin shape and file plan
- a plugin-engineering agent for scaffolding and wiring the actual files
- reusable skills for plugin scaffolding, MCP and agent setup, and marketplace publication
- a Playwright MCP server configuration for docs and marketplace verification workflows

## Files

```text
plugins/plugin-authoring-starter/
├── plugin.json
├── .mcp.json
├── README.md
├── agents/
│   ├── plugin-authoring-architect.agent.md
│   └── plugin-authoring-engineer.agent.md
└── skills/
    ├── plugin-marketplace-wiring/
    │   └── SKILL.md
    ├── plugin-mcp-and-agent-setup/
    │   └── SKILL.md
    └── plugin-scaffold-starter/
        └── SKILL.md
```

## Included agents

- `plugin-authoring-architect`
- `plugin-authoring-engineer`

## Included skills

- `plugin-scaffold-starter`
- `plugin-mcp-and-agent-setup`
- `plugin-marketplace-wiring`

## Local development

### Environment Variable Support

If you set the environment variable `PLUGIN_AUTHORING_SRC` to a local source folder, the authoring agents and skills will read from and write to that folder for agent and skill files. This allows you to save new or updated agent/skill definitions directly from your workspace, making it easy to persist LLM-generated solutions as reusable skills or agents.

Install the plugin from this repository checkout:

```sh
copilot plugin install ./plugins/plugin-authoring-starter
```

Because Copilot CLI caches installed plugin contents, reinstall the plugin after local edits:

```sh
copilot plugin install ./plugins/plugin-authoring-starter
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

Use the architecture agent to define a new plugin:

```sh
copilot --agent plugin-authoring-architect --prompt "Design a new plugin for release-note summarization with one agent, two skills, and MCP support"
```

Use the engineering agent to scaffold or update plugin files:

```sh
copilot --agent plugin-authoring-engineer --prompt "Create the plugin skeleton, wire marketplace metadata, and add an MCP config for docs verification"
```

## Recommended workflow

Start with `plugin-authoring-architect` when the plugin name, audience, or component mix is still fuzzy.

Move to `plugin-authoring-engineer` once you are ready to create or update files.

Use `plugin-marketplace-wiring` whenever the new plugin should be discoverable from `.github/plugin/marketplace.json` and the repository README.

## MCP note

The plugin ships a `.mcp.json` file that references the official Playwright MCP server package:

```json
{
  "servers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

This MCP config is useful when the plugin-authoring workflow needs to inspect GitHub Docs pages or validate marketplace pages with browser tooling.
