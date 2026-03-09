# Copilot Web News Plugins

This repository is a GitHub Copilot CLI plugin marketplace that follows the GitHub Docs guidance for:

- plugin marketplaces
- plugin manifests
- agent skills
- custom agents
- MCP server configuration

It currently publishes one plugin: `trusted-web-news`.

## Repository structure

```text
copilot-web-news-plugins/
├── .github/
│   └── plugin/
│       └── marketplace.json
└── plugins/
    └── trusted-web-news/
        ├── plugin.json
        ├── .mcp.json
        ├── agents/
        │   └── trusted-web-news-curator.agent.md
        └── skills/
            └── trusted-web-news/
                ├── SKILL.md
                └── trusted-sources.md
```

## Add this marketplace

```sh
copilot plugin marketplace add cmwen/copilot-web-news-plugins
```

Browse the marketplace:

```sh
copilot plugin marketplace browse copilot-web-news-plugins
```

Install the published plugin from the marketplace:

```sh
copilot plugin install trusted-web-news@copilot-web-news-plugins
```

You can also install the plugin directly from the repository path:

```sh
copilot plugin install cmwen/copilot-web-news-plugins:plugins/trusted-web-news
```

## What the plugin does

`trusted-web-news` helps Copilot gather same-day AI and web news from trusted sources, verify publication dates with browser tooling, and return the briefing in Traditional Chinese.

The default source set emphasizes official blogs and well-established engineering sources such as OpenAI, AWS, GitHub, Hugging Face, Cloudflare, WebKit, Mozilla, W3C, and web.dev.
