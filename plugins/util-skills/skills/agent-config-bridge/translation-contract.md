# Agent Config Bridge — Translation Contract

This document defines the inventory schema, plan schema, translation rules, and safety guarantees used by `scripts/agent_config_bridge.py`.

## Scan result schema

`scan` returns a JSON object with this structure:

```json
{
  "repo_root": "/abs/path/to/repo",
  "classification": "copilot|opencode|mixed|none",
  "copilot": {
    "plugin_roots": [
      {
        "root": "plugins/example-plugin",
        "plugin_json": "plugins/example-plugin/plugin.json",
        "mcp_json": "plugins/example-plugin/.mcp.json",
        "agents": ["plugins/example-plugin/agents/example.agent.md"],
        "skills": ["plugins/example-plugin/skills/example/SKILL.md"]
      }
    ],
    "mcp_files": ["plugins/example-plugin/.mcp.json"],
    "agents": ["plugins/example-plugin/agents/example.agent.md"],
    "skills": ["plugins/example-plugin/skills/example/SKILL.md"],
    "copilot_instructions": ".github/copilot-instructions.md",
    "instruction_files": [".github/instructions/team/shared.md"]
  },
  "opencode": {
    "config_files": [
      {
        "path": "opencode.jsonc",
        "format": "jsonc",
        "data": {
          "mcp": {
            "filesystem": {
              "type": "local",
              "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
              "enabled": true
            }
          }
        }
      }
    ],
    "skill_roots": [
      {
        "root": ".opencode",
        "skills": [".opencode/skills/review/SKILL.md"]
      }
    ],
    "skills": [".opencode/skills/review/SKILL.md"],
    "agents": [".opencode/agents/researcher.md"],
    "commands": [".opencode/commands/release.md"],
    "rules": ["AGENTS.md", "CLAUDE.md"]
  }
}
```

### Classification rules

- `copilot`: only Copilot-oriented assets were found
- `opencode`: only OpenCode-oriented assets were found
- `mixed`: both ecosystems were detected
- `none`: neither ecosystem was detected

## Translation plan schema

`plan` returns:

```json
{
  "repo_root": "/abs/path/to/repo",
  "classification": "mixed",
  "target": "copilot|opencode",
  "status": "ready|ambiguous|error",
  "source_root": "plugins/example-plugin",
  "target_root": ".opencode",
  "notes": ["Multiple OpenCode skill roots were found; pass --source-root explicitly."],
  "actions": [
    {
      "action": "link",
      "source": "plugins/example-plugin/skills/review/SKILL.md",
      "destination": ".opencode/skills/review/SKILL.md",
      "reason": "Copilot skills use SKILL.md and can be symlinked directly into OpenCode skill directories."
    },
    {
      "action": "write-file",
      "destination": ".opencode/agents/researcher.md",
      "reason": "Copilot agent markdown needs an OpenCode wrapper because the agent schemas differ.",
      "content": "# researcher\n..."
    },
    {
      "action": "write-json",
      "destination": "opencode.json",
      "reason": "Translate Copilot local MCP servers into OpenCode opencode.json format.",
      "data": {
        "mcp": {
          "filesystem": {
            "type": "local",
            "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
            "enabled": true
          }
        }
      }
    },
    {
      "action": "skip",
      "source": "opencode.jsonc",
      "reason": "MCP server remote-db: Only local OpenCode MCP servers can be translated into Copilot .mcp.json."
    }
  ]
}
```

### Action semantics

- `link`: create a relative symlink from destination to source
- `write-file`: create a generated markdown or text file
- `write-json`: create a generated JSON file using the supplied `data`
- `skip`: report a conflict, ambiguity, or unsupported translation without changing files

## Mapping table

| Source asset | Target asset | Strategy | Notes |
|---|---|---|---|
| Copilot `skills/<name>/SKILL.md` | OpenCode `.opencode/skills/<name>/SKILL.md` | `link` | Direct symlink, same Markdown skill shape |
| OpenCode `.opencode/skills/<name>/SKILL.md` | Copilot `skills/<name>/SKILL.md` | `link` | Also supports `.claude/skills` and `.agents/skills` source roots |
| Copilot `agents/<name>.agent.md` | OpenCode `.opencode/agents/<name>.md` | `write-file` | Wrapper preserves prompt body and provenance |
| OpenCode `.opencode/agents/<name>.md` | Copilot `agents/<name>.agent.md` | `write-file` | Wrapper adds Copilot frontmatter |
| Copilot `.mcp.json` local servers | OpenCode `opencode.json` `mcp` | `write-json` | Converts `{command,args}` to `{type:"local",command:[...],enabled:true}` |
| OpenCode `opencode.json` local `mcp` entries | Copilot `.mcp.json` | `write-json` | Converts `command:[cmd,...]` to `{command,args}` |
| OpenCode `.opencode/commands/<name>.md` | Copilot `skills/<name>/source-command.md` | `link` | Preserves original command text |
| OpenCode `.opencode/commands/<name>.md` | Copilot `skills/<name>/SKILL.md` | `write-file` | Wrapper explains imported command semantics |
| Copilot `.github/copilot-instructions.md` | OpenCode `AGENTS.md` | `link` | Only when no `AGENTS.md` exists |
| OpenCode `AGENTS.md` or `CLAUDE.md` | Copilot instructions | `skip` | Not auto-generated by this helper |

## Safe symlink rules

The helper only creates symlinks when all of the following are true:

1. The source path is inside the repository root.
2. The destination path is inside the repository root.
3. The destination does not already exist as a regular file.
4. The destination symlink either does not exist or already points to the correct source.
5. The symlink target is written as a **relative** path.

The helper refuses:

- repo-escape source paths
- repo-escape destination paths
- overwriting regular files
- replacing an existing symlink that points somewhere else

## Example plan: Copilot -> OpenCode

```json
{
  "target": "opencode",
  "status": "ready",
  "source_root": "plugins/sample-plugin",
  "target_root": ".opencode",
  "actions": [
    {
      "action": "link",
      "source": "plugins/sample-plugin/skills/triage/SKILL.md",
      "destination": ".opencode/skills/triage/SKILL.md",
      "reason": "Copilot skills use SKILL.md and can be symlinked directly into OpenCode skill directories."
    },
    {
      "action": "write-file",
      "destination": ".opencode/agents/researcher.md",
      "reason": "Copilot agent markdown needs an OpenCode wrapper because the agent schemas differ.",
      "content": "# researcher\n..."
    },
    {
      "action": "write-json",
      "destination": "opencode.json",
      "reason": "Translate Copilot local MCP servers into OpenCode opencode.json format.",
      "data": {
        "mcp": {
          "filesystem": {
            "type": "local",
            "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
            "enabled": true
          }
        }
      }
    }
  ]
}
```

## Example plan: OpenCode -> Copilot

```json
{
  "target": "copilot",
  "status": "ready",
  "source_root": ".opencode",
  "target_root": "plugins/demo-bridge",
  "actions": [
    {
      "action": "link",
      "source": ".opencode/skills/release/SKILL.md",
      "destination": "plugins/demo-bridge/skills/release/SKILL.md",
      "reason": "OpenCode skills are compatible with Copilot skill directories and can be symlinked directly."
    },
    {
      "action": "link",
      "source": ".opencode/commands/release.md",
      "destination": "plugins/demo-bridge/skills/release/source-command.md",
      "reason": "Keep the original OpenCode command markdown as a symlinked provenance file."
    },
    {
      "action": "write-file",
      "destination": "plugins/demo-bridge/skills/release/SKILL.md",
      "reason": "OpenCode commands need a Copilot SKILL.md wrapper that explains how to use the imported command template.",
      "content": "---\nname: release\n..."
    },
    {
      "action": "write-json",
      "destination": "plugins/demo-bridge/.mcp.json",
      "reason": "Translate local OpenCode MCP servers into Copilot .mcp.json format.",
      "data": {
        "servers": {
          "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"]
          }
        }
      }
    },
    {
      "action": "write-json",
      "destination": "plugins/demo-bridge/plugin.json",
      "reason": "Create a minimal Copilot plugin manifest for the generated bridge output.",
      "data": {
        "name": "demo-bridge",
        "description": "Bridge plugin generated from OpenCode sources in demo.",
        "version": "0.1.0",
        "keywords": ["bridge", "opencode", "copilot", "migration"],
        "skills": ["skills/"],
        "agents": "agents/",
        "mcpServers": ".mcp.json"
      }
    }
  ]
}
```
