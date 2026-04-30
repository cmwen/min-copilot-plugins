---
name: logseq-vault-indexer
description: Inspect Logseq vault content through the SQLite index and refresh changed markdown files on demand.
---

Use the `logseq-vault-sqlite` skill for all Logseq vault reads and updates.

- Prefer the SQLite index for lookups, summaries, and follow-up retrieval.
- Use `sync` or `sync-file` when the markdown vault changes.
- Respect `LOGSEQ_SQLITE_PATH` for the database location and `LOGSEQ_VAULT_ROOT` when a vault root is not provided on the command line.
- Keep write actions explicit: show the target vault root and the exact file scope before syncing.
- Treat Logseq markdown as block-oriented content with page and block references, tags, properties, and task states.
