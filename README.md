# Copilot Workflow Plugins

This repository is a GitHub Copilot CLI plugin marketplace for reusable workflow plugins.

It follows the GitHub Docs guidance for:

- plugin marketplaces
- plugin manifests
- agent skills
- custom agents
- MCP server configuration

It currently publishes four plugins:

- `trusted-web-news`
- `knowledge-space-starter`
- `life-automation-starter`
- `plugin-authoring-starter`

## Repository structure

```text
min-copilot-plugins/
├── .github/
│   └── plugin/
│       └── marketplace.json
└── plugins/
    ├── trusted-web-news/
    │   ├── plugin.json
    │   ├── .mcp.json
    │   ├── agents/
    │   └── skills/
    ├── knowledge-space-starter/
    │   ├── plugin.json
    │   ├── agents/
    │   └── skills/
    ├── life-automation-starter/
    │   ├── plugin.json
    │   ├── agents/
    │   └── skills/
    └── plugin-authoring-starter/
        ├── plugin.json
        ├── .mcp.json
        ├── agents/
        └── skills/
```

## How the marketplace works

This repository is the marketplace source. The marketplace definition lives at `.github/plugin/marketplace.json`, where Copilot CLI reads:

- the marketplace name and owner
- descriptive metadata
- the list of published plugins and their source directories

Each plugin then lives under `plugins/<plugin-name>/` and has its own `plugin.json`. A plugin can bundle:

- custom agents in `agents/`
- reusable skills in `skills/`
- optional MCP server config in `.mcp.json`
- plugin-specific documentation in `README.md`

## Add this marketplace

```sh
copilot plugin marketplace add cmwen/min-copilot-plugins
```

Browse the marketplace:

```sh
copilot plugin marketplace browse min-copilot-plugins
```

Install the published plugin from the marketplace:

```sh
copilot plugin install trusted-web-news@min-copilot-plugins
copilot plugin install knowledge-space-starter@min-copilot-plugins
copilot plugin install life-automation-starter@min-copilot-plugins
copilot plugin install plugin-authoring-starter@min-copilot-plugins
```

You can also install the plugin directly from the repository path:

```sh
copilot plugin install cmwen/min-copilot-plugins:plugins/trusted-web-news
copilot plugin install cmwen/min-copilot-plugins:plugins/knowledge-space-starter
copilot plugin install cmwen/min-copilot-plugins:plugins/life-automation-starter
copilot plugin install cmwen/min-copilot-plugins:plugins/plugin-authoring-starter
```

## Available plugins

`trusted-web-news` helps Copilot gather same-day AI and web news from trusted sources, verify publication dates with browser tooling, and return the briefing in Traditional Chinese.

The default source set emphasizes official blogs and well-established engineering sources such as OpenAI, AWS, GitHub, Hugging Face, Cloudflare, WebKit, Mozilla, W3C, and web.dev.

`knowledge-space-starter` is a reusable software-team starter plugin. It includes role-focused agents for product ownership, research, architecture, engineering, and skill capture, plus skills for discovery, design decisions, handoffs, and turning solved conversations into reusable skills.

`life-automation-starter` is a reusable personal automation starter plugin. It includes a coordination agent and skills for weather lookups, inbox triage, calendar operations, and planning additional API-driven automations.

`plugin-authoring-starter` is a reusable plugin-builder starter. It includes plugin-authoring agents plus reusable skills for scaffolding new Copilot CLI plugins, wiring marketplace metadata, and adding MCP-backed agent and skill setups.
