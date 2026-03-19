---
name: util-tmux-session-admin
description: Register repo memory and manage tmux-backed delegated worker sessions for external coding CLIs.
---

# Purpose

Use this skill when the user wants to remember a project's purpose and location, create or inspect tmux-managed worker sessions, or understand the current delegated-task queue for a repository.

This skill delegates all state management to `plugins/util-skills/scripts/tmux_cli_orchestrator.py`. It does **not** execute the repo task itself.

# Requirements

- Python 3 installed and available as `python3`.
- `tmux` installed and available on `PATH`.
- A local project directory the user wants to manage.

# Workflow

## Step 1 - Register or resolve the repository

Before managing sessions, register the repo so the helper can remember:

- the normalized repo path
- a short purpose
- an optional alias
- the default delegated CLI (`copilot` or `opencode`)

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  repo-register \
  --repo-root <repo-root> \
  --purpose "<short purpose>" \
  [--alias <repo-alias>] \
  [--default-cli <copilot|opencode>]
```

## Step 2 - Create or list worker sessions

Create a worker session when the repo needs a new visible tmux window/pane pair:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  session-create \
  --repo-root <repo-root> \
  [--label <session-label>] \
  [--cli <copilot|opencode>]
```

List sessions any time:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  session-list \
  --repo-root <repo-root>
```

## Step 3 - Show attach instructions or status

Return the tmux attach command and the current status summary instead of switching sessions silently:

```sh
python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  session-attach \
  --repo-root <repo-root>

python3 plugins/util-skills/scripts/tmux_cli_orchestrator.py \
  status-show \
  --repo-root <repo-root>
```

## Step 4 - Report the result clearly

Summarize:

- repo id, path, and purpose
- tmux session name
- session ids and whether each one is `idle` or `busy`
- queued and running task counts
- the exact attach command the user can run manually

# Allowlisted subcommands

| Subcommand | Description |
|------------|-------------|
| `repo-register` | Store or update repo memory (path, purpose, alias, default CLI). |
| `repo-list` | List every registered repo and its task/session counts. |
| `repo-show` | Show one registered repo with task/session state. |
| `session-create` | Create a tmux worker window with runner and status panes. |
| `session-list` | List worker sessions for a repo. |
| `session-attach` | Return the tmux attach command for a repo session set. |
| `status-show` | Show the current repo/session/task summary. |

# Safety rules

1. Do not treat session creation as task execution. Registering repos and creating tmux worker windows is safe to do before any delegated task is queued.
2. Do not invent repo purpose text. Use the user's wording or ask them for a concise purpose if it is unclear.
3. Do not attach or switch the user's terminal automatically. Return the attach command and let the user decide when to enter tmux.
4. Surface missing local runtime support explicitly. If `tmux` is missing, say so and stop.
5. Preserve the repo memory in the helper-managed state directory; do not write orchestration state into the repository itself.

# Output expectations

Reply with:

```text
Repo: <repo-id> - <purpose>
Path: <repo-root>
Tmux: <tmux-session-name>
Sessions:
- <session-id> - <idle|busy>
Attach: <tmux attach-session -t ...>
Task counts: queued=<n>, running=<n>, completed=<n>, failed=<n>, cancelled=<n>
```
