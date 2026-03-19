# KeePass Entity Ops — Operation Contract

This document defines the JSON spec structure accepted by `keepass_safe_ops.py` for each allowlisted subcommand. All specs are passed via `--spec-file <path>`.

> **Delete operations are not defined here and are not supported.** Any spec containing `delete`, `remove`, `purge`, `trash`, or `recycle_bin` keys will be rejected by the script.

## open-database

Opens the database, validates access, and creates a local session metadata file. The password must **never** appear in the spec.

```json
{
  "session_name": "work-vault",
  "database_path": "/absolute/path/to/vault.kdbx",
  "key_file_path": "/absolute/path/to/vault.keyx"
}
```

| Field           | Required | Description                                              |
|-----------------|----------|----------------------------------------------------------|
| `session_name`  | Yes      | Logical name for the session (used in lock files).       |
| `database_path` | Yes      | Absolute path to the `.kdbx` file.                       |
| `key_file_path` | No       | Absolute path to the KeePass key file, if used.          |

The script writes a session metadata file at `~/.keepass_sessions/<session_name>.json` containing `session_name`, `database_path`, `key_file_path`, `opened_at`, and `last_used_at`. The password is never written.

---

## close-database

Removes the session metadata file. Does not require a password.

```json
{
  "session_name": "work-vault"
}
```

| Field          | Required | Description                          |
|----------------|----------|--------------------------------------|
| `session_name` | Yes      | Name of the session to close.        |

---

## create-entity

Creates a new entry or group. The database is opened from the active session, a timestamped backup is made, the entity is created, and the database is saved.

### Create an entry

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "entry",
  "group_path": ["Social", "Networking"],
  "title": "LinkedIn",
  "username": "user@example.com",
  "url": "https://www.linkedin.com",
  "notes": "Professional account"
}
```

### Create a group

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "group",
  "parent_group_path": ["Work"],
  "name": "Dev Tools"
}
```

| Field               | Required for entry | Required for group | Description                                              |
|---------------------|--------------------|--------------------|----------------------------------------------------------|
| `session_name`      | Yes                | Yes                | Active session name.                                     |
| `confirmed`         | Yes                | Yes                | Must be `true` after the user explicitly approves the exact spec. |
| `entity_type`       | Yes                | Yes                | `"entry"` or `"group"`.                                  |
| `group_path`        | Yes (entry)        | No                 | Path to the parent group for the new entry.              |
| `parent_group_path` | No                 | Yes (group)        | Path to the parent group for the new group.              |
| `title`             | Yes                | No                 | Entry title.                                             |
| `username`          | No                 | No                 | Entry username.                                          |
| `url`               | No                 | No                 | Entry URL.                                               |
| `notes`             | No                 | No                 | Entry or group notes.                                    |
| `name`              | No                 | Yes                | New group name.                                          |

> **Note:** The entry password is read from the `KEEPASS_ENTRY_PASSWORD` environment variable, not the spec file.

---

## move-entity

Moves an existing entry or group to a different group.

### Move an entry

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "entry",
  "source_path": ["Social", "LinkedIn"],
  "target_group_path": ["Work", "Networking"]
}
```

### Move a group

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "group",
  "source_path": ["Old Folder", "SubFolder"],
  "target_group_path": ["Archive"]
}
```

| Field               | Required | Description                                              |
|---------------------|----------|----------------------------------------------------------|
| `session_name`      | Yes      | Active session name.                                     |
| `confirmed`         | Yes      | Must be `true` after the user explicitly approves the exact spec. |
| `entity_type`       | Yes      | `"entry"` or `"group"`.                                  |
| `source_path`       | Yes      | Full path to the entity to move (last segment is name/title). |
| `target_group_path` | Yes      | Full path to the destination group.                      |

---

## edit-entity

Edits fields of an existing entry or group.

### Edit an entry

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "entry",
  "source_path": ["Work", "Dev Tools", "GitHub"],
  "fields": {
    "title": "GitHub (work)",
    "username": "work-user",
    "url": "https://github.com",
    "notes": "Work GitHub account"
  }
}
```

### Edit a group

```json
{
  "session_name": "work-vault",
  "confirmed": true,
  "entity_type": "group",
  "source_path": ["Old Name"],
  "fields": {
    "name": "New Name",
    "notes": "Renamed group"
  }
}
```

| Field          | Required | Description                                              |
|----------------|----------|----------------------------------------------------------|
| `session_name` | Yes      | Active session name.                                     |
| `confirmed`    | Yes      | Must be `true` after the user explicitly approves the exact spec. |
| `entity_type`  | Yes      | `"entry"` or `"group"`.                                  |
| `source_path`  | Yes      | Full path to the entity to edit.                         |
| `fields`       | Yes      | Object with one or more fields to update.                |

Allowed entry fields: `title`, `username`, `url`, `notes`. The entry password can be changed by setting `KEEPASS_ENTRY_PASSWORD` before running the command with a `change_password: true` flag in `fields`.

Allowed group fields: `name`, `notes`.

> **Unrecognised fields are rejected.** The script will error rather than silently ignore unknown field names.

---

## Forbidden patterns

The script explicitly rejects specs or environment conditions that match any of the following:

- Any key named `delete`, `remove`, `purge`, `trash`, `recycle`, or `recycle_bin`.
- Any `entity_type` value other than `"entry"` or `"group"`.
- Any `subcommand` not in the allowlist (`open-database`, `close-database`, `create-entity`, `move-entity`, `edit-entity`, `search-entries`, `show-entity`, `forget`).
- Any write-action spec that omits `confirmed: true`.
- Missing required fields for the chosen subcommand.
- A `database_path` or `source_path` that contains traversal sequences (`..`).
- Any target path segment or group name containing delete-like terms such as `trash`, `recycle bin`, `purge`, or `remove`.

---

## search-entries

Searches for entries by title or username within the database or a specific group. This is a read-only operation.

```json
{
  "session_name": "work-vault",
  "search_term": "gmail",
  "group_path": ["Social"]
}
```

| Field         | Required | Description                                              |
|---------------|----------|----------------------------------------------------------|
| `session_name` | Yes      | Active session name.                                     |
| `search_term` | No       | Text to search for in title or username (case-insensitive). If omitted, lists all entries in the scope. |
| `group_path`  | No       | If provided, search only within this group. Omit to search all entries. |

---

## show-entity

Displays details of a specific entry or group. This is a read-only operation.

```json
{
  "session_name": "work-vault",
  "entity_type": "entry",
  "source_path": ["Work", "GitHub"]
}
```

| Field          | Required | Description                                              |
|----------------|----------|----------------------------------------------------------|
| `session_name` | Yes      | Active session name.                                     |
| `entity_type`  | Yes      | `"entry"` or `"group"`.                                  |
| `source_path`  | Yes      | Full path to the entity to display.                      |

---

## forget

Alias for `close-database`. Closes the database session without requiring explicit database operations.

```json
{
  "session_name": "work-vault"
}
```

| Field          | Required | Description                          |
|----------------|----------|--------------------------------------|
| `session_name` | Yes      | Name of the session to forget/close. |
