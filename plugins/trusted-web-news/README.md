# trusted-web-news

`trusted-web-news` is a GitHub Copilot CLI plugin that bundles:

- a reusable agent skill for trusted AI and web news aggregation
- a custom agent tuned for this news workflow
- a Playwright MCP server configuration for browsing and extraction

## Files

```text
plugins/trusted-web-news/
├── plugin.json
├── .mcp.json
├── agents/
│   └── trusted-web-news-curator.agent.md
└── skills/
    └── trusted-web-news/
        ├── SKILL.md
        └── trusted-sources.md
```

## Local development

Install the plugin from this repository checkout:

```sh
copilot plugin install ./plugins/trusted-web-news
```

Because Copilot CLI caches installed plugin contents, reinstall the plugin after local edits:

```sh
copilot plugin install ./plugins/trusted-web-news
```

## Usage

Check that the plugin loaded:

```sh
copilot plugin list
```

List skills:

```text
/skills list
```

Use the custom agent:

```sh
copilot --agent trusted-web-news-curator --prompt "Summarize today's AI and web news in Traditional Chinese"
```

Example interactive prompt:

```text
Use the trusted-web-news skill to summarize today's AI and web news from trusted sources in Traditional Chinese.
```

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

The user's Copilot environment must support MCP and allow the configured server to run.
