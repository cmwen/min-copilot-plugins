---
name: util-delegated-cli-task-ops
description: Queue and run delegated repo tasks inside tmux-managed worker sessions using external coding CLIs such as Copilot or OpenCode.
---

# Purpose

Use this skill when the user wants to delegate a repo task to a managed tmux session instead of having the current conversation execute the work directly.

This skill uses `plugins/util-skills/scripts/tmux_cli_orchestrator.py` for queueing and scheduling and `plugins/util-skills/scripts/tmux_cli_worker.py` for execution inside the tmux worker pane.

# Requirements

- Python 3 installed and available as `python3`.
- `tmux` installed and available on `PATH`.
- A registered repository and at least one worker session (the helper can auto-create one if needed).
- A supported delegated CLI adapter on `PATH`:
  - `copilot`
  - `opencode`

# Workflow

## Step 1 - Confirm repo/session context

Before enqueuing a task, verify the repo and session state:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  status-show \
  --repo-root <repo-root>
```

If the repo is not registered yet, register it first with `util-tmux-session-admin`.

## Step 2 - Build the delegated task prompt

Create the full task prompt text. For lengthy or structured prompts, save the prompt to a temporary file and pass the file path to the helper.

Use one of these forms:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-enqueue \
  --repo-root <repo-root> \
  --cli <copilot|opencode> \
  --prompt "<delegated task prompt>"
```

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-enqueue \
  --repo-root <repo-root> \
  --cli <copilot|opencode> \
  --prompt-file /tmp/delegated-task.md
```

Optional controls:

- `--title <title>` for a short label
- `--session-id <session-id>` to prefer a specific worker session
- `--execution-mode queue` to serialize work on the main checkout (default)
- `--execution-mode worktree` to isolate the task in a git worktree
- `--agent <agent-name>` or `--model <model-name>` to pass through adapter-specific preferences

## Step 3 - Respect queue vs. worktree safety

Default behavior is conservative:

- only one `queue` task runs against the main checkout at a time
- extra `queue` tasks remain queued until the current main-checkout task finishes
- `worktree` tasks can run concurrently when the repo is a git repo and an idle worker session exists

If `worktree` mode is requested for a non-git repo, stop and surface the error instead of silently downgrading.

## Step 4 - Inspect task state

Use the helper to show the queue or one specific task:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-list \
  --repo-root <repo-root>

python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-show \
  --repo-root <repo-root> \
  --task-id <task-id>
```

When a task finishes, the worker updates tmux state, writes the final summary into the log, and sends a best-effort OS notification.

## Step 5 - Cancel only queued tasks

If a queued task should not run:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  task-cancel \
  --repo-root <repo-root> \
  --task-id <task-id>
```

Running task cancellation is intentionally manual because the live CLI process is inside tmux.

# Allowlisted subcommands

| Subcommand | Description |
|------------|-------------|
| `task-enqueue` | Queue a task and start it immediately when safe and possible. |
| `task-start-next` | Start any queued task that is eligible to run now. |
| `task-list` | List delegated tasks for the repo. |
| `task-show` | Show one delegated task in detail. |
| `task-cancel` | Cancel a queued task before execution. |

# Safety rules

1. Do not execute the user's repo task directly in the current conversation. Always enqueue it through the helper so it runs inside the managed tmux worker.
2. Default to `queue` mode unless the user clearly wants isolated concurrent work and the repo can support git worktrees.
3. Surface missing adapters (`copilot`, `opencode`) or missing `tmux` as explicit errors.
4. Do not claim a queued task is running. Report the exact status returned by the helper.
5. Keep the user informed about where to inspect results: tmux session name, session id, task id, and log file path.

# Output expectations

Reply with:

```text
Task: <task-id> - <title>
Status: <queued|running|completed|failed|cancelled>
CLI: <copilot|opencode>
Mode: <queue|worktree>
Session: <session-id or pending>
Log: <log-file or pending>
Tmux: <tmux-session-name>
Next: <attach command or queue note>
```
