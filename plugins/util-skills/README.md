# util-skills

Utility skills for GitHub Copilot CLI. Provides focused, safety-first skills for operations on local data files and repository bridge workflows.

## Files

```text
plugins/util-skills/
├── plugin.json
├── README.md
├── skills/
│   ├── agent-config-bridge/
│   │   ├── SKILL.md
│   │   └── translation-contract.md
│   └── keepass-entity-ops/
│       ├── SKILL.md
│       └── operation-contract.md
├── scripts/
│   ├── agent_config_bridge.py
│   └── keepass_safe_ops.py
└── tests/
    ├── test_agent_config_bridge.py
    └── test_keepass_safe_ops.py
```

## Included skills

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

The `agent_config_bridge.py` helper is standard-library-only and does not require additional Python packages.

### Run the tests

```sh
cd plugins/util-skills
python3 -m unittest discover -s tests -v
```

All tests in `tests/test_keepass_safe_ops.py` and `tests/test_agent_config_bridge.py` use only the standard library.

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

Then invoke a skill in Copilot:

```text
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
- **Passwords are never stored.** For KeePass operations, the master password must be supplied via `KEEPASS_PASSWORD`, and entry passwords use `KEEPASS_ENTRY_PASSWORD`.
- **Write actions require explicit confirmation.** Copilot must show the full KeePass operation spec and ask for `yes/no` confirmation before running `create-entity`, `move-entity`, or `edit-entity`.
- **Automatic backups.** Every KeePass write operation makes a timestamped `.backup.<timestamp>.kdbx` copy next to the original before touching the database.
- **Delete operations are refused.** KeePass delete-like operations are rejected entirely.
