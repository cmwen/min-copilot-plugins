# util-tmux-session-admin contract

The helper prints structured JSON for every subcommand.

## `repo-register`

Request:

```text
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  repo-register \
  --repo-root <repo-root> \
  --purpose "<purpose>" \
  [--alias <alias>] \
  [--default-cli <copilot|opencode>]
```

Response shape:

```json
{
  "repo": {
    "repo_id": "demo-1234abcd",
    "repo_path": "/absolute/path/to/repo",
    "purpose": "Short repo purpose",
    "alias": "demo",
    "default_cli": "copilot",
    "tmux_session_name": "util-demo-1234abcd"
  },
  "session_count": 1,
  "task_counts": {
    "queued": 0,
    "running": 0,
    "completed": 0,
    "failed": 0,
    "cancelled": 0
  }
}
```

## `session-create`

Response shape:

```json
{
  "repo": {"repo_id": "demo-1234abcd"},
  "session": {
    "session_id": "main",
    "status": "idle",
    "runner_pane_id": "%5",
    "status_pane_id": "%6",
    "window_name": "main",
    "tmux_session_name": "util-demo-1234abcd"
  },
  "attach_command": "tmux attach-session -t util-demo-1234abcd"
}
```

## `status-show`

Response shape:

```json
{
  "repo": {...},
  "sessions": [...],
  "task_counts": {...},
  "active_tasks": [...],
  "queued_tasks": [...]
}
```

## Error handling

Errors are emitted as JSON:

```json
{
  "error": "Human-readable explanation"
}
```
