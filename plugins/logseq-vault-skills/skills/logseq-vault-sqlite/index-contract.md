# Logseq vault SQLite contract

## Database location

The helper script reads the SQLite path from `LOGSEQ_SQLITE_PATH` unless `--db-path` is supplied.

## Schema

### `pages`

- `page_name` primary key
- `file_path` unique file location in the vault
- `title`
- `content_hash`
- `mtime`
- `indexed_at`
- `properties_json`

### `blocks`

- `id` autoincrement primary key
- `page_name`
- `file_path`
- `line_no`
- `parent_line_no`
- `indent`
- `marker`
- `text`
- `task_state`
- `properties_json`
- `tags_json`
- `page_refs_json`
- `block_refs_json`

### `blocks_fts`

FTS5 index for `page_name`, `text`, `tags`, `refs`, and `properties`.

## Commands

- `sync --vault-root PATH [--prune]`
- `sync-file PATH`
- `search QUERY`
- `show-page PAGE_NAME`

## Update behavior

- File-level sync replaces the existing rows for that file before inserting the new page and blocks.
- `--prune` removes database rows for files that no longer exist in the vault root.
- Query commands never modify the database.
