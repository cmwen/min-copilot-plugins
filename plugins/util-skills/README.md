# util-skills

Utility agents and skills for GitHub Copilot CLI. This plugin provides focused, safety-first building blocks for local data operations, repository bridge workflows, and tmux-managed delegated coding sessions.

## Files

```text
plugins/util-skills/
├── plugin.json
├── README.md
├── agents/
│   └── util-tmux-cli-orchestrator.agent.md
├── skills/
│   ├── agent-config-bridge/
│   │   ├── SKILL.md
│   │   └── translation-contract.md
│   ├── keepass-entity-ops/
│   │   ├── SKILL.md
│   │   └── operation-contract.md
│   ├── util-delegated-cli-task-ops/
│   │   ├── SKILL.md
│   │   └── task-contract.md
│   └── util-tmux-session-admin/
│       ├── SKILL.md
│       └── session-contract.md
├── scripts/
│   ├── agent_config_bridge.py
│   ├── keepass_safe_ops.py
│   ├── tmux_cli_orchestrator.py
│   └── tmux_cli_worker.py
└── tests/
    ├── test_agent_config_bridge.py
    ├── test_keepass_safe_ops.py
    ├── test_tmux_cli_orchestrator.py
    └── test_tmux_cli_worker.py
```

## Included agent

### `util-tmux-cli-orchestrator`

Coordinate long-running repo work through managed tmux worker sessions instead of executing the repository task directly in the current Copilot conversation.

The agent remembers each repo's normalized path and purpose, uses tmux worker windows and panes to keep delegated sessions visible, and routes repo work through the tmux-oriented skills below.

## Included skills

### `util-tmux-session-admin`

Register repo memory and manage tmux-backed worker windows for delegated coding sessions.

Supported helper subcommands:

| Subcommand | Description |
|------------|-------------|
| `repo-register` | Store or update repo memory, including purpose, normalized path, alias, and default delegated CLI. |
| `repo-list` | List registered repos and their task/session counts. |
| `repo-show` | Show one repo with its current task/session state. |
| `session-create` | Create a worker window with runner and status panes inside the repo tmux session. |
| `session-list` | List worker sessions for a repo. |
| `session-attach` | Return the tmux attach command for the repo session. |
| `status-show` | Show the current repo/session/task summary. |

The helper persists orchestration state under `~/.copilot-util-skills/tmux-orchestrator` so repo memory, session metadata, queue state, logs, and prompt files stay outside the repository.

See [`skills/util-tmux-session-admin/SKILL.md`](skills/util-tmux-session-admin/SKILL.md) and [`skills/util-tmux-session-admin/session-contract.md`](skills/util-tmux-session-admin/session-contract.md).

### `util-delegated-cli-task-ops`

Queue and run delegated coding tasks inside managed tmux workers using supported external CLIs.

Supported helper subcommands:

| Subcommand | Description |
|------------|-------------|
| `task-enqueue` | Queue a task and start it immediately when the repo/session state allows. |
| `task-start-next` | Start any queued task that is now eligible to run. |
| `task-list` | List delegated tasks for a repo. |
| `task-show` | Show one delegated task in detail. |
| `task-cancel` | Cancel a queued task before it starts. |

The scheduler is conservative by default: only one `queue` task may run on a repo's main checkout at a time, while `worktree` tasks can run concurrently when the repo is a git repository and an idle worker session exists.

Currently validated delegated adapters:

- `copilot`
- `opencode`

See [`skills/util-delegated-cli-task-ops/SKILL.md`](skills/util-delegated-cli-task-ops/SKILL.md) and [`skills/util-delegated-cli-task-ops/task-contract.md`](skills/util-delegated-cli-task-ops/task-contract.md).

### `keepass-entity-ops`

Perform safe, auditable operations on KeePass `.kdbx` databases via a local Python helper script. Supported operations:

| Subcommand       | Description |
|------------------|-------------|
| `open-database`  | Validate access and create a local session file. |
| `close-database` | Remove the local session file. |
| `create-entity`  | Create a new entry or group (with backup). |
| `move-entity`    | Move an existing entry or group (with backup). |
| `edit-entity`    | Edit fields of an existing entry or group (with backup). |

**Delete operations are not supported and will be refused.**

See [`skills/keepass-entity-ops/SKILL.md`](skills/keepass-entity-ops/SKILL.md) for the full workflow and safety rules, and [`skills/keepass-entity-ops/operation-contract.md`](skills/keepass-entity-ops/operation-contract.md) for the JSON spec format for each subcommand.

### `agent-config-bridge`

Analyze a repository and bridge agent-related configuration between GitHub Copilot CLI and OpenCode using a standard-library-only Python helper.

Supported helper subcommands:

| Subcommand | Description |
|------------|-------------|
| `scan` | Inventory Copilot-oriented and OpenCode-oriented assets and classify the repository as `copilot`, `opencode`, `mixed`, or `none`. |
| `plan` | Produce an explicit translation plan with `link`, `write-file`, `write-json`, and `skip` actions. |
| `apply` | Execute an approved plan safely using relative symlinks and generated wrapper/config files. |

The bridge prefers direct relative symlinks for compatible skill Markdown, generates wrappers where schemas differ, translates only local MCP server definitions, and refuses to overwrite existing regular files.

See [`skills/agent-config-bridge/SKILL.md`](skills/agent-config-bridge/SKILL.md) for the operator workflow and [`skills/agent-config-bridge/translation-contract.md`](skills/agent-config-bridge/translation-contract.md) for the scan schema, plan schema, mapping rules, and example plans.

## Local development

### Prerequisites

- Python 3.9+
- `pykeepass` (only required for live KeePass database operations; tests run without it):

```sh
pip install pykeepass
```

The `agent_config_bridge.py`, `tmux_cli_orchestrator.py`, and `tmux_cli_worker.py` helpers are standard-library-only and do not require additional Python packages.

Delegated tmux sessions also require:

- `tmux`
- at least one supported delegated CLI adapter (`copilot` or `opencode`)
- `git` when using worktree execution mode

### Run the tests

```sh
cd plugins/util-skills
python3 -m unittest discover -s tests -v
```

All tests in `tests/test_keepass_safe_ops.py`, `tests/test_agent_config_bridge.py`, `tests/test_tmux_cli_orchestrator.py`, and `tests/test_tmux_cli_worker.py` use only the standard library.

### Run the scripts manually

```sh
# KeePass session open
KEEPASS_PASSWORD='your-master-password' \
  python3 scripts/keepass_safe_ops.py open-database \
    --spec-file /tmp/open_spec.json

# Bridge scan
python3 scripts/agent_config_bridge.py scan \
  --repo-root /path/to/repo

# Bridge plan toward Copilot
python3 scripts/agent_config_bridge.py plan \
  --repo-root /path/to/repo \
  --target copilot \
  --source-root .opencode

# Register a repo for delegated tmux sessions
python3 scripts/tmux_cli_orchestrator.py repo-register \
  --repo-root /path/to/repo \
  --purpose "Long-running app work managed through tmux" \
  --default-cli copilot

# Create a worker session
python3 scripts/tmux_cli_orchestrator.py session-create \
  --repo-root /path/to/repo \
  --label backend

# Queue delegated work from a prompt file
python3 scripts/tmux_cli_orchestrator.py task-enqueue \
  --repo-root /path/to/repo \
  --cli opencode \
  --prompt-file /tmp/delegated-task.md \
  --execution-mode worktree
```

## Usage

Install the plugin:

```sh
copilot plugin install util-skills@min-copilot-plugins
```

Or directly:

```sh
copilot plugin install cmwen/min-copilot-plugins:plugins/util-skills
```

Then invoke a bundled agent or skill in Copilot:

```text
@copilot use util-tmux-cli-orchestrator to register this repo, create a tmux worker, and queue a long-running refactor task for Copilot CLI
@copilot /util-tmux-session-admin register this repo for delegated sessions with purpose "CLI orchestration experiments"
@copilot /util-delegated-cli-task-ops enqueue a worktree-isolated OpenCode task from /tmp/delegated-task.md
@copilot /keepass-entity-ops open-database for my work vault at /path/to/work.kdbx
@copilot /keepass-entity-ops create a new entry "GitHub" in the "Dev Tools" group
@copilot /agent-config-bridge scan this repository and plan a bridge from OpenCode to Copilot
@copilot /agent-config-bridge plan a Copilot-to-OpenCode bridge for plugins/util-skills into .opencode
```

## Safety and configuration notes

- **Repository bridge writes require explicit confirmation.** The skill must present the exact `plan` output and get explicit yes/no approval before `apply` is run.
- **Relative symlinks only.** The bridge helper creates relative symlinks for compatible files and refuses repo-escape sources or targets.
- **No silent overwrites.** Existing non-symlink files are treated as conflicts and are not replaced automatically.
- **Transparent translation.** Agents and command wrappers preserve provenance, and remote or otherwise unsupported MCP entries are reported as `skip` actions.
- **Delegated tasks stay out of the repo.** Repo memory, task metadata, prompt files, logs, and worktree bookkeeping live under `~/.copilot-util-skills/tmux-orchestrator`.
- **Queue mode is the safe default.** Only one delegated task runs on a repo's main checkout at a time unless the task is explicitly isolated with `--execution-mode worktree`.
- **Tmux and OS notifications are visible hints, not hidden state.** The worker writes the final summary into the task log, updates tmux panes, and sends a best-effort OS notification without masking failures if notifications are unavailable.
- **Passwords are never stored.** For KeePass operations, the master password must be supplied via `KEEPASS_PASSWORD`, and entry passwords use `KEEPASS_ENTRY_PASSWORD`.
- **Write actions require explicit confirmation.** Copilot must show the full KeePass operation spec and ask for `yes/no` confirmation before running `create-entity`, `move-entity`, or `edit-entity`.
- **Automatic backups.** Every KeePass write operation makes a timestamped `.backup.<timestamp>.kdbx` copy next to the original before touching the database.
- **Delete operations are refused.** KeePass delete-like operations are rejected entirely.
