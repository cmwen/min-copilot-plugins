# life-automation-starter

`life-automation-starter` is a GitHub Copilot CLI plugin for personal workflow automation.

It bundles:

- a coordination agent for everyday automation tasks
- reusable skills for weather, email, calendar, and API-driven workflows
- safe starter guidance that assumes you will connect your own accounts, MCP servers, or authenticated tools

## Files

```text
plugins/life-automation-starter/
├── plugin.json
├── agents/
│   └── life-automation-orchestrator.agent.md
└── skills/
    ├── life-api-automation/
    │   └── SKILL.md
    ├── life-calendar-ops/
    │   └── SKILL.md
    ├── life-email-triage/
    │   └── SKILL.md
    └── life-weather-briefing/
        └── SKILL.md
```

## Included agent

- `life-automation-orchestrator`

## Local development

Install the plugin from this repository checkout:

```sh
copilot plugin install ./plugins/life-automation-starter
```

Because Copilot CLI caches installed plugin contents, reinstall the plugin after local edits:

```sh
copilot plugin install ./plugins/life-automation-starter
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

Use the coordination agent:

```sh
copilot --agent life-automation-orchestrator --prompt "Summarize tomorrow's weather, my urgent emails, and scheduling conflicts"
```

## Configuration note

This plugin does not ship credentials or provider-specific secrets.

Pair it with the tools available in your Copilot environment, such as:

- provider-specific MCP servers
- authenticated APIs
- browser tooling you explicitly approve

For write actions like sending mail or creating events, require explicit confirmation before execution.
