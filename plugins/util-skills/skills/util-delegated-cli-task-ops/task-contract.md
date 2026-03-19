# util-delegated-cli-task-ops contract

The helper prints structured JSON describing the queued or running task.

## `task-enqueue`

Request:

```text
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-enqueue \
  --repo-root <repo-root> \
  --cli <copilot|opencode> \
  --prompt-file /tmp/task.md \
  [--title <title>] \
  [--session-id <session-id>] \
  [--execution-mode <queue|worktree>] \
  [--agent <agent-name>] \
  [--model <model-name>]
```

Response shape:

```json
{
  "task": {
    "task_id": "9f2c4a7b1d2e",
    "title": "Investigate flaky tests",
    "status": "running",
    "cli": "copilot",
    "execution_mode": "queue",
    "session_id": "main",
    "log_file": "/Users/example/.copilot-util-skills/tmux-orchestrator/repos/demo/logs/9f2c4a7b1d2e.log",
    "prompt_file": "/Users/example/.copilot-util-skills/tmux-orchestrator/repos/demo/prompts/9f2c4a7b1d2e.md",
    "worktree_path": null
  },
  "scheduling": {
    "repo_id": "demo-1234abcd",
    "started_task_ids": ["9f2c4a7b1d2e"],
    "remaining_queued": 0
  }
}
```

## `task-show`

Response shape:

```json
{
  "task": {
    "task_id": "9f2c4a7b1d2e",
    "status": "completed",
    "summary": "Delegated copilot task exited with code 0 in /path/to/repo (...)",
    "notification_method": "osascript",
    "worktree_path": null
  }
}
```

## `task-cancel`

Only queued tasks are cancellable. Running tasks return an error so the operator can decide how to interrupt the live tmux pane.

## Error handling

Errors are emitted as JSON:

```json
{
  "error": "Human-readable explanation"
}
```
