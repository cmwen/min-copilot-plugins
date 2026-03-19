"""
Tests for keepass_safe_ops.py

Focused on validation, safety rules, and spec-parsing logic.
All tests run without pykeepass installed and without a real KeePass database.
Uses only the Python standard library.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# ---------------------------------------------------------------------------
# Load the module under test via importlib so pykeepass is not required at
# module-import time (the script lazily imports it inside _import_pykeepass).
# ---------------------------------------------------------------------------

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "keepass_safe_ops.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("keepass_safe_ops", MODULE_PATH)
keepass_safe_ops = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(keepass_safe_ops)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_spec(tmp_dir: str, data: dict) -> str:
    path = os.path.join(tmp_dir, "spec.json")
    with open(path, "w") as fh:
        json.dump(data, fh)
    return path


# ---------------------------------------------------------------------------
# load_spec
# ---------------------------------------------------------------------------

class TestLoadSpec(unittest.TestCase):

    def test_raises_file_not_found_for_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            keepass_safe_ops.load_spec("/nonexistent/path/spec.json")

    def test_raises_value_error_for_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "spec.json")
            with open(path, "w") as fh:
                json.dump(["not", "an", "object"], fh)
            with self.assertRaises(ValueError):
                keepass_safe_ops.load_spec(path)

    def test_valid_spec_returns_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {"session_name": "s1", "database_path": "/x/y.kdbx"})
            spec = keepass_safe_ops.load_spec(path)
            self.assertIsInstance(spec, dict)
            self.assertEqual(spec["session_name"], "s1")


# ---------------------------------------------------------------------------
# _check_no_forbidden_keys
# ---------------------------------------------------------------------------

class TestForbiddenKeys(unittest.TestCase):

    def _check(self, spec):
        keepass_safe_ops._check_no_forbidden_keys(spec)

    def test_delete_key_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            self._check({"delete": "something"})
        self.assertIn("delete", str(ctx.exception).lower())

    def test_remove_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"remove": True})

    def test_purge_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"purge": True})

    def test_trash_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"trash": "bin"})

    def test_recycle_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"recycle": True})

    def test_recycle_bin_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"recycle_bin": "path"})

    def test_safe_spec_passes(self):
        # Should not raise
        self._check({"session_name": "x", "entity_type": "entry"})

    def test_multiple_forbidden_keys_reported(self):
        with self.assertRaises(ValueError) as ctx:
            self._check({"delete": True, "purge": True})
        msg = str(ctx.exception)
        self.assertIn("delete", msg.lower())

    def test_nested_forbidden_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self._check({"fields": {"delete": True}})


# ---------------------------------------------------------------------------
# _check_no_path_traversal
# ---------------------------------------------------------------------------

class TestPathTraversal(unittest.TestCase):

    def test_traversal_in_database_path_is_rejected(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._check_no_path_traversal("/home/user/../etc/passwd")

    def test_normal_path_passes(self):
        keepass_safe_ops._check_no_path_traversal("/home/user/vaults/work.kdbx")

    def test_traversal_in_source_path_segment_is_rejected(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._check_path_segments(["Work", ".."], "source_path")

    def test_separator_in_path_segment_is_rejected(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._check_path_segments(
                ["Work/Subgroup"], "target_group_path"
            )


class TestForbiddenTargets(unittest.TestCase):

    def test_target_group_path_rejects_recycle_bin(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._check_no_forbidden_targets(
                {"target_group_path": ["Archive", "Recycle Bin"]}
            )

    def test_safe_target_group_path_passes(self):
        keepass_safe_ops._check_no_forbidden_targets(
            {"target_group_path": ["Archive", "Reference"]}
        )


# ---------------------------------------------------------------------------
# _check_entity_type
# ---------------------------------------------------------------------------

class TestEntityType(unittest.TestCase):

    def test_entry_is_valid(self):
        keepass_safe_ops._check_entity_type("entry")  # no raise

    def test_group_is_valid(self):
        keepass_safe_ops._check_entity_type("group")  # no raise

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            keepass_safe_ops._check_entity_type("folder")
        self.assertIn("folder", str(ctx.exception))

    def test_delete_as_entity_type_is_rejected(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._check_entity_type("delete")


# ---------------------------------------------------------------------------
# _require helper
# ---------------------------------------------------------------------------

class TestRequire(unittest.TestCase):

    def test_raises_when_field_missing(self):
        with self.assertRaises(ValueError) as ctx:
            keepass_safe_ops._require({"a": 1}, "a", "b")
        self.assertIn("b", str(ctx.exception))

    def test_passes_when_all_present(self):
        keepass_safe_ops._require({"a": 1, "b": 2}, "a", "b")  # no raise


class TestWriteConfirmation(unittest.TestCase):

    def test_missing_confirmation_is_rejected(self):
        with self.assertRaises(ValueError):
            keepass_safe_ops._require_write_confirmation({})

    def test_confirmation_true_is_accepted(self):
        keepass_safe_ops._require_write_confirmation({"confirmed": True})


# ---------------------------------------------------------------------------
# Argument parser — allowlist enforcement
# ---------------------------------------------------------------------------

class TestParser(unittest.TestCase):

    def _parse(self, *args):
        return keepass_safe_ops.build_parser().parse_args(list(args))

    def test_valid_subcommand_accepted(self):
        args = self._parse("open-database", "--spec-file", "/tmp/s.json")
        self.assertEqual(args.subcommand, "open-database")

    def test_all_allowlisted_subcommands_accepted(self):
        for sub in keepass_safe_ops.ALLOWLISTED_SUBCOMMANDS:
            args = self._parse(sub, "--spec-file", "/tmp/s.json")
            self.assertEqual(args.subcommand, sub)

    def test_unlisted_subcommand_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("delete-entity", "--spec-file", "/tmp/s.json")

    def test_spec_file_required(self):
        with self.assertRaises(SystemExit):
            self._parse("open-database")


# ---------------------------------------------------------------------------
# main() — spec file safety gate
# ---------------------------------------------------------------------------

class TestMainSafetyGate(unittest.TestCase):

    def test_missing_spec_file_returns_error_code(self):
        rc = keepass_safe_ops.main(
            ["open-database", "--spec-file", "/tmp/does_not_exist_abc123.json"]
        )
        self.assertNotEqual(rc, 0)

    def test_spec_with_forbidden_key_returns_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp,
                {
                    "session_name": "s",
                    "database_path": "/x/y.kdbx",
                    "delete": True,
                },
            )
            rc = keepass_safe_ops.main(["open-database", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_missing_password_env_var_returns_error_code(self):
        """open-database should fail gracefully when KEEPASS_PASSWORD is unset."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a dummy kdbx path (existence check happens inside pykeepass,
            # but the password check fires before that in cmd_open_database).
            path = _write_spec(
                tmp,
                {"session_name": "s", "database_path": "/tmp/fake.kdbx"},
            )
            env = {k: v for k, v in os.environ.items() if k != "KEEPASS_PASSWORD"}
            with mock.patch.dict(os.environ, env, clear=True):
                rc = keepass_safe_ops.main(["open-database", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_write_operation_without_confirmation_returns_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp,
                {
                    "session_name": "s",
                    "entity_type": "group",
                    "parent_group_path": ["Work"],
                    "name": "Dev Tools",
                },
            )
            with mock.patch.object(
                keepass_safe_ops,
                "_open_db_from_session",
                side_effect=AssertionError("should not reach DB"),
            ):
                rc = keepass_safe_ops.main(["create-entity", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_write_operation_with_delete_like_target_returns_error_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp,
                {
                    "session_name": "s",
                    "confirmed": True,
                    "entity_type": "entry",
                    "source_path": ["Work", "GitHub"],
                    "target_group_path": ["Archive", "Recycle Bin"],
                },
            )
            rc = keepass_safe_ops.main(["move-entity", "--spec-file", path])
            self.assertNotEqual(rc, 0)


# ---------------------------------------------------------------------------
# cmd_edit_entity — field validation (no DB required)
# ---------------------------------------------------------------------------

class TestEditEntityFieldValidation(unittest.TestCase):
    """
    These tests exercise the field-name validation that fires before the
    database is opened.  We mock _open_db_from_session so no real DB is needed.
    """

    def _run_edit(self, spec):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, spec)
            with mock.patch.object(
                keepass_safe_ops,
                "_open_db_from_session",
                side_effect=AssertionError("should not reach DB"),
            ):
                return keepass_safe_ops.main(["edit-entity", "--spec-file", path])

    def test_unknown_entry_field_returns_error(self):
        spec = {
            "session_name": "s",
            "confirmed": True,
            "entity_type": "entry",
            "source_path": ["Group", "Title"],
            "fields": {"nonexistent_field": "value"},
        }
        rc = self._run_edit(spec)
        self.assertNotEqual(rc, 0)

    def test_unknown_group_field_returns_error(self):
        spec = {
            "session_name": "s",
            "confirmed": True,
            "entity_type": "group",
            "source_path": ["OldName"],
            "fields": {"color": "red"},
        }
        rc = self._run_edit(spec)
        self.assertNotEqual(rc, 0)

    def test_empty_fields_returns_error(self):
        spec = {
            "session_name": "s",
            "confirmed": True,
            "entity_type": "entry",
            "source_path": ["Group", "Title"],
            "fields": {},
        }
        rc = self._run_edit(spec)
        self.assertNotEqual(rc, 0)


class TestCreateGroupNotes(unittest.TestCase):

    def test_group_notes_are_applied_after_creation(self):
        class FakeGroup:
            def __init__(self):
                self.notes = None

        class FakeKeePass:
            def __init__(self):
                self.created_group = FakeGroup()
                self.saved = False

            def add_group(self, parent_group, name):
                self.parent_group = parent_group
                self.group_name = name
                return self.created_group

            def save(self):
                self.saved = True

        class NoOpLock:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        fake_kp = FakeKeePass()
        spec = {
            "session_name": "s",
            "confirmed": True,
            "entity_type": "group",
            "parent_group_path": ["Work"],
            "name": "Dev Tools",
            "notes": "Tooling-related entries",
        }

        with mock.patch.object(
            keepass_safe_ops,
            "_open_db_from_session",
            return_value=(fake_kp, "/tmp/work.kdbx"),
        ), mock.patch.object(
            keepass_safe_ops,
            "_resolve_group",
            return_value=object(),
        ), mock.patch.object(
            keepass_safe_ops,
            "DatabaseLock",
            NoOpLock,
        ), mock.patch.object(
            keepass_safe_ops,
            "_make_backup",
            return_value="/tmp/work.backup.kdbx",
        ):
            keepass_safe_ops.cmd_create_entity(spec)

        self.assertEqual(fake_kp.created_group.notes, "Tooling-related entries")
        self.assertTrue(fake_kp.saved)


# ---------------------------------------------------------------------------
# Forbidden subcommand patterns
# ---------------------------------------------------------------------------

class TestForbiddenSubcommandPattern(unittest.TestCase):

    def test_pattern_matches_delete(self):
        pattern = keepass_safe_ops.FORBIDDEN_SUBCOMMAND_PATTERNS
        self.assertIsNotNone(pattern.search("delete-entity"))

    def test_pattern_matches_remove(self):
        pattern = keepass_safe_ops.FORBIDDEN_SUBCOMMAND_PATTERNS
        self.assertIsNotNone(pattern.search("remove-entry"))

    def test_pattern_does_not_match_create(self):
        pattern = keepass_safe_ops.FORBIDDEN_SUBCOMMAND_PATTERNS
        self.assertIsNone(pattern.search("create-entity"))

    def test_pattern_does_not_match_edit(self):
        pattern = keepass_safe_ops.FORBIDDEN_SUBCOMMAND_PATTERNS
        self.assertIsNone(pattern.search("edit-entity"))


# ---------------------------------------------------------------------------
# Session path helpers (no FS side effects — just test logic)
# ---------------------------------------------------------------------------

class TestSessionPath(unittest.TestCase):

    def test_session_path_uses_sessions_dir(self):
        path = keepass_safe_ops._session_path("my-session")
        self.assertTrue(str(path).endswith("my-session.json"))
        self.assertIn(".keepass_sessions", str(path))

    def test_load_session_raises_for_missing_session(self):
        with mock.patch.object(
            keepass_safe_ops.SESSIONS_DIR.__class__,
            "__truediv__",
            return_value=Path("/tmp/nonexistent_session_abc123.json"),
        ):
            # Patch _session_path to return a non-existent path
            with mock.patch.object(
                keepass_safe_ops,
                "_session_path",
                return_value=Path("/tmp/nonexistent_session_abc123.json"),
            ):
                with self.assertRaises(FileNotFoundError):
                    keepass_safe_ops._load_session("no-such-session")


# ---------------------------------------------------------------------------
# search-entries operation
# ---------------------------------------------------------------------------

class TestSearchEntries(unittest.TestCase):

    def test_search_entries_requires_session_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {})
            rc = keepass_safe_ops.main(["search-entries", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_search_entries_does_not_require_confirmation(self):
        """search-entries is read-only and should not require confirmed: true."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {"session_name": "s"})
            with mock.patch.object(
                keepass_safe_ops,
                "_open_db_from_session",
                return_value=(mock.MagicMock(), "/tmp/db.kdbx"),
            ):
                rc = keepass_safe_ops.main(["search-entries", "--spec-file", path])
                self.assertEqual(rc, 0)

    def test_search_entries_with_invalid_group_path_type(self):
        """group_path must be a list."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp,
                {"session_name": "s", "group_path": "NotAList"}
            )
            rc = keepass_safe_ops.main(["search-entries", "--spec-file", path])
            self.assertNotEqual(rc, 0)


# ---------------------------------------------------------------------------
# show-entity operation
# ---------------------------------------------------------------------------

class TestShowEntity(unittest.TestCase):

    def test_show_entity_requires_session_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {"entity_type": "entry"})
            rc = keepass_safe_ops.main(["show-entity", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_show_entity_requires_entity_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {"session_name": "s"})
            rc = keepass_safe_ops.main(["show-entity", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_show_entity_requires_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp, {"session_name": "s", "entity_type": "entry"}
            )
            rc = keepass_safe_ops.main(["show-entity", "--spec-file", path])
            self.assertNotEqual(rc, 0)

    def test_show_entity_does_not_require_confirmation(self):
        """show-entity is read-only and should not require confirmed: true."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(
                tmp,
                {
                    "session_name": "s",
                    "entity_type": "entry",
                    "source_path": ["Work", "GitHub"],
                }
            )
            with mock.patch.object(
                keepass_safe_ops,
                "_open_db_from_session",
                return_value=(mock.MagicMock(), "/tmp/db.kdbx"),
            ):
                rc = keepass_safe_ops.main(["show-entity", "--spec-file", path])
                self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# forget operation (alias for close-database)
# ---------------------------------------------------------------------------

class TestForgetOperation(unittest.TestCase):

    def test_forget_is_an_alias_for_close_database(self):
        """forget should work exactly like close-database."""
        with tempfile.TemporaryDirectory() as tmp:
            session_path = keepass_safe_ops._session_path("test-session")
            session_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            session_path.write_text('{"session_name": "test-session"}')

            path = _write_spec(tmp, {"session_name": "test-session"})
            # Verify session exists before forget
            self.assertTrue(session_path.is_file())

            # Run forget
            rc = keepass_safe_ops.main(["forget", "--spec-file", path])
            self.assertEqual(rc, 0)

            # Verify session is deleted (same as close-database)
            self.assertFalse(session_path.is_file())

    def test_forget_handles_missing_session_gracefully(self):
        """forget on missing session should not error (like close-database)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_spec(tmp, {"session_name": "nonexistent"})
            rc = keepass_safe_ops.main(["forget", "--spec-file", path])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
