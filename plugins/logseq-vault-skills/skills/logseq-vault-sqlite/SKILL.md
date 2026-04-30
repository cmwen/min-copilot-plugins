---
name: logseq-vault-sqlite
description: Index Logseq markdown into SQLite, query the index quickly, and synchronize markdown updates back into the database.
---

# Purpose

Use this skill when the user wants to read, search, or refresh a Logseq vault without repeatedly parsing raw markdown. The helper script stores page and block data in SQLite so lookups stay fast even when the vault grows.

## Environment variables

- `LOGSEQ_SQLITE_PATH`: absolute or user-relative path to the SQLite database file. This controls where the Logseq index is stored.
- `LOGSEQ_VAULT_ROOT`: optional default Logseq vault root when the user does not pass `--vault-root`.

# Workflow

1. Identify whether the request is a read, sync, or file-level update.
2. Resolve the vault root and SQLite path before running any command.
3. Use `search` or `show-page` for fast retrieval from the SQLite index.
4. Use `sync-file` for a single changed markdown page or `sync` for a broader vault refresh.
5. If `--prune` is involved, explain that stale database rows will be removed and ask for explicit confirmation before proceeding.

# Supported helper commands

| Command | Purpose | Notes |
|---------|---------|-------|
| `sync` | Index every markdown page under the vault root | Supports `--prune` to remove missing pages |
| `sync-file` | Re-index one Logseq markdown file | Updates the page and block rows for that file |
| `search` | Query the SQLite index | Uses FTS-backed search with a fallback `LIKE` scan |
| `show-page` | Return one page and its indexed blocks | Useful for inspecting the exact stored structure |

# Output format

When describing a sync, report:

- the database path
- the vault root
- how many files were indexed, skipped, or pruned

When describing a search or page lookup, report:

- the matched page name
- the line number or block scope
- the matching text snippet

# Quality bar

- Prefer the SQLite index over rescanning raw markdown.
- Preserve Logseq-specific structures such as tags, references, properties, and task states.
- Do not overwrite the database path silently; always honor `LOGSEQ_SQLITE_PATH` when it is set.
