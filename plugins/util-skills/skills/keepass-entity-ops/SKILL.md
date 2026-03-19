---
name: keepass-entity-ops
description: Perform safe, auditable open, close, create, move, and edit operations on KeePass databases via a local Python helper script.
---

# Purpose

Use this skill when the user wants to inspect, search, or modify entries and groups inside a KeePass `.kdbx` database file. It delegates all database access to `plugins/util-skills/scripts/keepass_safe_ops.py`, which enforces session management, per-database locking, timestamped backups, and an explicit allowlist of safe subcommands.

**Delete-like operations are unsupported and must be refused.** Do not attempt to remove, delete, trash, purge, or move entries or groups to a recycle bin. If the user requests any such action, decline clearly and explain that only create, move, edit, search, and show are available.

# Requirements

- Python 3 installed and available as `python3` or `python`.
- `pykeepass` installed in the Python environment: `pip install pykeepass`.
- A valid `.kdbx` database file accessible on the local filesystem.
- A KeePass master password (provided at runtime; never stored or logged).
- Optional: a KeePass key file path.

# Workflow

## Step 1 — Understand the request

Identify the target entity type (`entry` or `group`), the desired operation, and all required fields. Restate the intended change back to the user in plain language before running any command.

## Step 2 — Confirm before every write action

**Before running `create-entity`, `move-entity`, or `edit-entity`, you MUST obtain explicit written confirmation from the user.** Present the full operation spec (entity type, target path, fields to write) and ask: *"Shall I proceed with this change? (yes/no)"* Do not proceed until the user confirms.

`open-database` and `close-database` do not require additional confirmation beyond the user asking for them.

## Step 3 — Build the spec file

Construct a JSON spec file matching the operation contract in `operation-contract.md` and save it to a temporary path (e.g. `/tmp/keepass_op_spec.json`). Never include the database password in the spec file.

For `create-entity`, `move-entity`, and `edit-entity`, add `"confirmed": true` to the spec file only after the user explicitly approves the exact spec you showed them.

## Step 4 — Run the helper script

```sh
python3 plugins/util-skills/scripts/keepass_safe_ops.py <subcommand> \
    --spec-file /tmp/keepass_op_spec.json
```

Pass the database password via the `KEEPASS_PASSWORD` environment variable:

```sh
KEEPASS_PASSWORD='...' python3 plugins/util-skills/scripts/keepass_safe_ops.py <subcommand> \
    --spec-file /tmp/keepass_op_spec.json
```

## Step 5 — Report the result

Parse stdout/stderr from the script. If the script exits non-zero, surface the error message verbatim and do not retry silently. If the operation succeeded, confirm the action taken (e.g. "Entry 'Gmail' created in group 'Social'.").

## Step 6 — Clean up

Delete the temporary spec file after the script completes, regardless of success or failure.

# Allowlisted subcommands

| Subcommand       | Entity types   | Requires confirmation |
|------------------|----------------|-----------------------|
| `open-database`  | n/a            | No                    |
| `close-database` | n/a            | No                    |
| `create-entity`  | entry, group   | **Yes**               |
| `move-entity`    | entry, group   | **Yes**               |
| `edit-entity`    | entry, group   | **Yes**               |
| `search-entries` | entry          | No (read-only)        |
| `show-entity`    | entry, group   | No (read-only)        |
| `forget`         | n/a            | No (alias for close)  |

# Safety rules

1. **Never store or log the database password.** Pass it only via the `KEEPASS_PASSWORD` environment variable, and never include it in spec files, chat messages, or command history.
2. **Never skip confirmation for write actions.** Even if the user says "just do it", always confirm the specific spec before executing, and include `"confirmed": true` in the spec only after that approval.
3. **Refuse delete-like operations.** If the user requests delete, remove, purge, trash, recycle, or any destructive action, decline and explain the restriction.
4. **Do not modify spec files after showing them to the user.** What the user confirmed is exactly what must be executed.
5. **Surface all errors explicitly.** Do not hide or downplay script failures.
6. **Do not run the script with elevated privileges** (sudo, root) unless the user explicitly owns the database path and understands the implications.

# Output format

After a successful operation, reply with:

```
✅ <Subcommand> completed.
Entity: <type> — <name or title>
Location: <group path>
Backup: <backup file path>
```

After a failed operation, reply with:

```
❌ <Subcommand> failed.
Error: <verbatim error message from the script>
No changes were saved.
```
