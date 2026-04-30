import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "logseq_vault_sqlite.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("logseq_vault_sqlite", MODULE_PATH)
logseq_vault_sqlite = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = logseq_vault_sqlite
MODULE_SPEC.loader.exec_module(logseq_vault_sqlite)


class LogseqVaultSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_page(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_resolve_db_path_uses_environment_variable(self) -> None:
        with mock.patch.dict(
            os.environ,
            {logseq_vault_sqlite.DB_PATH_ENV: str(self.root / "logseq.sqlite3")},
            clear=False,
        ):
            resolved = logseq_vault_sqlite.resolve_db_path(None)

        self.assertEqual(resolved, self.root / "logseq.sqlite3")

    def test_parse_logseq_markdown_extracts_blocks_and_properties(self) -> None:
        page_path = self._write_page(
            "pages/Project Alpha.md",
            """status:: active
# Project Alpha
- TODO Build the index #project [[Home]]
  priority:: high
  - child note ((abc123))

General note about the project.
""",
        )

        parsed = logseq_vault_sqlite.parse_logseq_markdown(page_path)

        self.assertEqual(parsed.page_name, "Project Alpha")
        self.assertEqual(parsed.title, "Project Alpha")
        self.assertEqual(parsed.properties, {"status": "active"})
        self.assertEqual(len(parsed.blocks), 3)
        self.assertEqual(parsed.blocks[0].task_state, "TODO")
        self.assertEqual(parsed.blocks[0].tags, ["project"])
        self.assertEqual(parsed.blocks[0].page_refs, ["Home"])
        self.assertEqual(parsed.blocks[0].properties, {"priority": "high"})
        self.assertEqual(parsed.blocks[2].marker, "paragraph")

    def test_sync_and_search_vault(self) -> None:
        page_path = self._write_page(
            "pages/Project Alpha.md",
            """status:: active
- TODO Build the index #project [[Home]]
  - child note ((abc123))
""",
        )
        db_path = self.root / "logseq.sqlite3"

        with logseq_vault_sqlite.connect_database(db_path) as conn:
            sync_result = logseq_vault_sqlite.sync_file(conn, page_path)
            self.assertEqual(sync_result["indexed"], 2)
            self.assertEqual(sync_result["skipped"], 0)
            self.assertEqual(
                logseq_vault_sqlite.stats(conn),
                {"pages": 1, "blocks": 2},
            )

            rows = logseq_vault_sqlite.search_index(conn, "Build", 10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["page_name"], "Project Alpha")
            self.assertIn("Build the index", rows[0]["text"])

            page = logseq_vault_sqlite.show_page(conn, "Project Alpha")
            self.assertEqual(page["page"]["title"], "Project Alpha")
            self.assertEqual(len(page["blocks"]), 2)

    def test_prune_removes_deleted_pages(self) -> None:
        self._write_page("pages/One.md", "- first block\n")
        second = self._write_page("pages/Two.md", "- second block\n")
        db_path = self.root / "logseq.sqlite3"

        with logseq_vault_sqlite.connect_database(db_path) as conn:
            logseq_vault_sqlite.sync_vault(conn, self.root, prune=False)
            self.assertEqual(logseq_vault_sqlite.stats(conn), {"pages": 2, "blocks": 2})

            second.unlink()
            result = logseq_vault_sqlite.sync_vault(conn, self.root, prune=True)

            self.assertEqual(result["pruned"], 1)
            self.assertEqual(logseq_vault_sqlite.stats(conn), {"pages": 1, "blocks": 1})


if __name__ == "__main__":
    unittest.main()
