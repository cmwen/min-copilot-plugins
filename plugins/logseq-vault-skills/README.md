# logseq-vault-skills

Logseq vault agents and skills for GitHub Copilot CLI. This plugin keeps a local SQLite index of Logseq markdown pages and blocks so reads are fast and writes stay explicit.

## Files

```text
plugins/logseq-vault-skills/
├── plugin.json
├── README.md
├── agents/
│   └── logseq-vault-indexer.agent.md
├── scripts/
│   └── logseq_vault_sqlite.py
└── skills/
    └── logseq-vault-sqlite/
        ├── SKILL.md
        └── index-contract.md
```

## Included agent

### `logseq-vault-indexer`

Use the SQLite index to inspect Logseq pages and blocks before falling back to raw markdown scans. When the vault changes, synchronize the affected files into the database with the helper script instead of parsing the whole vault repeatedly.

## Included skill

### `logseq-vault-sqlite`

Index Logseq markdown into a local SQLite database, query the index for fast reads, and sync file changes back into the database.

The helper script understands common Logseq markdown patterns, including:

- bullet and paragraph blocks
- page and block references
- tags
- task states such as `TODO`, `DOING`, and `DONE`
- `key:: value` properties at page or block scope

## Configuration

Set the SQLite database location with:

```sh
export LOGSEQ_SQLITE_PATH="$HOME/.copilot/logseq/logseq.sqlite3"
```

The vault root can also be supplied explicitly with `--vault-root` or via:

```sh
export LOGSEQ_VAULT_ROOT="/path/to/your/logseq-vault"
```

## Local development

### Requirements

- Python 3.9+

### Run the tests

```sh
cd plugins/logseq-vault-skills
python3 -m unittest discover -s tests -v
```

### Common commands

```sh
python3 scripts/logseq_vault_sqlite.py sync --vault-root /path/to/logseq
python3 scripts/logseq_vault_sqlite.py sync-file /path/to/logseq/pages/Project.md
python3 scripts/logseq_vault_sqlite.py search "project alpha"
python3 scripts/logseq_vault_sqlite.py show-page "Project Alpha"
```

## Usage

Install the plugin:

```sh
copilot plugin install logseq-vault-skills@min-copilot-plugins
```

Or directly from the repository:

```sh
copilot plugin install cmwen/min-copilot-plugins:plugins/logseq-vault-skills
```

Then invoke the bundled agent or skill in Copilot:

```text
@copilot use logseq-vault-indexer to inspect the Logseq vault through the SQLite index and refresh the database for the changed markdown files
@copilot /logseq-vault-sqlite sync the vault at /path/to/logseq into the configured SQLite database
@copilot /logseq-vault-sqlite search the index for "design review"
```
