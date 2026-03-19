"""
keepass_safe_ops.py — Safe, auditable KeePass operations helper.

Allowlisted subcommands:
  open-database    Validate access and create a local session metadata file.
  close-database   Remove the session metadata file.
  create-entity    Create a new entry or group (with backup).
  move-entity      Move an existing entry or group (with backup).
  edit-entity      Edit fields of an existing entry or group (with backup).
  search-entries   Search for entries by title or username (read-only).
  show-entity      Display entry or group details (read-only).
  forget           Alias for close-database.

Delete-like operations (delete, remove, purge, trash, recycle) are explicitly
rejected by construction.  The script errors rather than silently swallowing
any failure.

Usage:
  KEEPASS_PASSWORD='...' python3 keepass_safe_ops.py <subcommand> \
      --spec-file /tmp/op_spec.json

For create-entity / edit-entity with a new entry password supply:
  KEEPASS_ENTRY_PASSWORD='...'

pykeepass is imported lazily so that validation-only paths (argument parsing,
spec validation, safety checks) can run and be tested without pykeepass
installed.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWLISTED_SUBCOMMANDS = {
    "open-database",
    "close-database",
    "create-entity",
    "move-entity",
    "edit-entity",
    "search-entries",
    "show-entity",
    "forget",
}

FORBIDDEN_KEYS = frozenset(
    {"delete", "remove", "purge", "trash", "recycle", "recycle_bin"}
)

FORBIDDEN_SUBCOMMAND_PATTERNS = re.compile(
    r"\b(delete|remove|purge|trash|recycle)\b", re.IGNORECASE
)
FORBIDDEN_TARGET_PATTERNS = re.compile(
    r"\b(delete|remove|purge|trash|recycle(?:[-_ ]?bin)?)\b", re.IGNORECASE
)
PATH_LIST_FIELDS = (
    "group_path",
    "parent_group_path",
    "source_path",
    "target_group_path",
)
STRING_PATH_FIELDS = ("database_path", "key_file_path")

SESSIONS_DIR = Path.home() / ".keepass_sessions"
LOCKS_DIR = Path.home() / ".keepass_locks"

ALLOWED_ENTRY_FIELDS = frozenset(
    {"title", "username", "url", "notes", "change_password"}
)
ALLOWED_GROUP_FIELDS = frozenset({"name", "notes"})


# ---------------------------------------------------------------------------
# Lazy pykeepass import
# ---------------------------------------------------------------------------

def _import_pykeepass():
    """Import pykeepass lazily.  Raises ImportError with a helpful message."""
    try:
        from pykeepass import PyKeePass  # noqa: PLC0415
        return PyKeePass
    except ImportError as exc:
        raise ImportError(
            "pykeepass is required for database operations. "
            "Install it with: pip install pykeepass"
        ) from exc


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

def _check_no_forbidden_keys(spec: dict[str, Any]) -> None:
    """Raise ValueError if the spec contains any forbidden key names."""

    def _walk(node: Any, location: str) -> None:
        if isinstance(node, dict):
            found = FORBIDDEN_KEYS & set(node.keys())
            if found:
                raise ValueError(
                    f"Spec contains forbidden key(s) at {location}: {sorted(found)}. "
                    "Delete-like operations are not supported."
                )
            for key, value in node.items():
                _walk(value, f"{location}.{key}")
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, f"{location}[{idx}]")

    _walk(spec, "root")


def _check_no_path_traversal(path_value: str) -> None:
    """Raise ValueError if a path string contains traversal sequences."""
    if ".." in Path(path_value).parts:
        raise ValueError(
            f"Path traversal sequence detected in: {path_value!r}"
        )


def _check_path_segments(path_value: Any, field_name: str) -> None:
    """Validate a JSON path-list field used for KeePass groups or entries."""
    if not isinstance(path_value, list):
        raise ValueError(f"{field_name} must be a list of path segments.")
    for index, segment in enumerate(path_value):
        if not isinstance(segment, str) or not segment:
            raise ValueError(
                f"{field_name}[{index}] must be a non-empty string path segment."
            )
        if "/" in segment or "\\" in segment:
            raise ValueError(
                f"{field_name}[{index}] must not contain path separators: {segment!r}"
            )
        if ".." in Path(segment).parts:
            raise ValueError(
                f"Path traversal sequence detected in {field_name}[{index}]: "
                f"{segment!r}"
            )


def _check_entity_type(entity_type: str) -> None:
    if entity_type not in ("entry", "group"):
        raise ValueError(
            f"entity_type must be 'entry' or 'group', got: {entity_type!r}"
        )


def _check_no_forbidden_targets(spec: dict[str, Any]) -> None:
    """Reject delete-adjacent target names or paths by construction."""

    def _check_string(value: str, location: str) -> None:
        if FORBIDDEN_TARGET_PATTERNS.search(value):
            raise ValueError(
                f"Delete-like target content is not supported in {location}: "
                f"{value!r}"
            )

    for field_name in (
        "group_path",
        "parent_group_path",
        "source_path",
        "target_group_path",
    ):
        value = spec.get(field_name)
        if isinstance(value, list):
            for idx, segment in enumerate(value):
                if isinstance(segment, str):
                    _check_string(segment, f"{field_name}[{idx}]")

    if isinstance(spec.get("name"), str):
        _check_string(spec["name"], "name")

    fields = spec.get("fields")
    if isinstance(fields, dict) and isinstance(fields.get("name"), str):
        _check_string(fields["name"], "fields.name")


def _require_write_confirmation(spec: dict[str, Any]) -> None:
    if spec.get("confirmed") is not True:
        raise ValueError(
            "Write operations require explicit confirmation in the spec. "
            "Set 'confirmed': true only after the user approves the exact change."
        )


# ---------------------------------------------------------------------------
# Spec loading and validation helpers
# ---------------------------------------------------------------------------

def load_spec(spec_file: str) -> dict[str, Any]:
    """Load and return the JSON spec, applying top-level safety checks."""
    path = Path(spec_file)
    if not path.is_file():
        raise FileNotFoundError(f"Spec file not found: {spec_file}")
    with path.open() as fh:
        spec = json.load(fh)
    if not isinstance(spec, dict):
        raise ValueError("Spec must be a JSON object.")
    _check_no_forbidden_keys(spec)
    _check_no_forbidden_targets(spec)
    for field_name in STRING_PATH_FIELDS:
        value = spec.get(field_name)
        if isinstance(value, str):
            _check_no_path_traversal(value)
    for field_name in PATH_LIST_FIELDS:
        if field_name in spec:
            _check_path_segments(spec[field_name], field_name)
    return spec


def _require(spec: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in spec]
    if missing:
        raise ValueError(f"Spec is missing required field(s): {missing}")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_path(session_name: str) -> Path:
    SESSIONS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{session_name}.json"


def _load_session(session_name: str) -> dict[str, Any]:
    path = _session_path(session_name)
    if not path.is_file():
        raise FileNotFoundError(
            f"No active session '{session_name}'. "
            "Run open-database first."
        )
    with path.open() as fh:
        return json.load(fh)


def _save_session(session_name: str, data: dict[str, Any]) -> None:
    path = _session_path(session_name)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=2)
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------

class DatabaseLock:
    """Advisory per-database lock using a lock file and fcntl."""

    def __init__(self, database_path: str) -> None:
        LOCKS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Use a safe filename derived from the db path hash
        import hashlib  # noqa: PLC0415
        db_hash = hashlib.sha1(database_path.encode()).hexdigest()[:12]
        self._lock_path = LOCKS_DIR / f"{db_hash}.lock"
        self._fh = None

    def acquire(self) -> None:
        self._fh = self._lock_path.open("w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(
                f"Could not acquire lock for database "
                f"(another process may be using it): {exc}"
            ) from exc

    def release(self) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "DatabaseLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


# ---------------------------------------------------------------------------
# Backup helper
# ---------------------------------------------------------------------------

def _make_backup(database_path: str) -> str:
    """Copy the kdbx to a timestamped backup file next to the original."""
    src = Path(database_path)
    if not src.is_file():
        raise FileNotFoundError(f"Database file not found: {database_path}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = src.parent / f"{src.stem}.backup.{ts}{src.suffix}"
    shutil.copy2(src, backup_path)
    return str(backup_path)


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_open_database(spec: dict[str, Any]) -> None:
    _require(spec, "session_name", "database_path")

    session_name: str = spec["session_name"]
    database_path: str = spec["database_path"]
    key_file_path: str | None = spec.get("key_file_path")

    _check_no_path_traversal(database_path)
    if key_file_path:
        _check_no_path_traversal(key_file_path)

    password = os.environ.get("KEEPASS_PASSWORD")
    if not password:
        raise ValueError(
            "KEEPASS_PASSWORD environment variable is not set. "
            "Provide the database master password via this variable."
        )

    PyKeePass = _import_pykeepass()
    # Validate access — will raise CredentialsError or FileNotFoundError on failure
    kp = PyKeePass(database_path, password=password, keyfile=key_file_path)
    # Quick read probe to ensure the database loaded correctly
    _ = kp.root_group

    now = datetime.now(timezone.utc).isoformat()
    session_data: dict[str, Any] = {
        "session_name": session_name,
        "database_path": database_path,
        "opened_at": now,
        "last_used_at": now,
    }
    if key_file_path:
        session_data["key_file_path"] = key_file_path

    _save_session(session_name, session_data)
    print(
        f"Session '{session_name}' opened. "
        f"Database: {database_path}"
    )


def cmd_close_database(spec: dict[str, Any]) -> None:
    _require(spec, "session_name")
    session_name: str = spec["session_name"]
    path = _session_path(session_name)
    if path.is_file():
        path.unlink()
        print(f"Session '{session_name}' closed.")
    else:
        print(f"No active session '{session_name}' found; nothing to close.")


def _open_db_from_session(session_name: str):  # returns PyKeePass instance
    session = _load_session(session_name)
    database_path: str = session["database_path"]
    key_file_path: str | None = session.get("key_file_path")

    password = os.environ.get("KEEPASS_PASSWORD")
    if not password:
        raise ValueError(
            "KEEPASS_PASSWORD environment variable is not set."
        )

    PyKeePass = _import_pykeepass()
    kp = PyKeePass(database_path, password=password, keyfile=key_file_path)

    # Update last_used_at
    session["last_used_at"] = datetime.now(timezone.utc).isoformat()
    _save_session(session_name, session)

    return kp, database_path


def _resolve_group(kp, path: list[str]):
    """Resolve a group by path list.  Raises ValueError if not found."""
    if not path:
        return kp.root_group
    group = kp.find_groups(path=path, first=True)
    if group is None:
        raise ValueError(f"Group not found at path: {path}")
    return group


def cmd_create_entity(spec: dict[str, Any]) -> None:
    _require(spec, "session_name", "entity_type")
    _require_write_confirmation(spec)
    session_name: str = spec["session_name"]
    entity_type: str = spec["entity_type"]
    _check_entity_type(entity_type)

    kp, database_path = _open_db_from_session(session_name)

    with DatabaseLock(database_path):
        backup_path = _make_backup(database_path)

        if entity_type == "entry":
            _require(spec, "group_path", "title")
            group_path: list[str] = spec["group_path"]
            title: str = spec["title"]
            username: str = spec.get("username", "")
            url: str = spec.get("url", "")
            notes: str = spec.get("notes", "")
            entry_password: str = os.environ.get("KEEPASS_ENTRY_PASSWORD", "")

            parent_group = _resolve_group(kp, group_path)
            kp.add_entry(parent_group, title, username, entry_password, url=url, notes=notes)
            kp.save()
            print(
                f"Entry '{title}' created in group {group_path}.\n"
                f"Backup: {backup_path}"
            )

        else:  # group
            _require(spec, "parent_group_path", "name")
            parent_group_path: list[str] = spec["parent_group_path"]
            name: str = spec["name"]
            notes: str | None = spec.get("notes")

            parent_group = _resolve_group(kp, parent_group_path)
            created_group = kp.add_group(parent_group, name)
            if notes is not None:
                created_group.notes = notes
            kp.save()
            print(
                f"Group '{name}' created under {parent_group_path}.\n"
                f"Backup: {backup_path}"
            )


def cmd_move_entity(spec: dict[str, Any]) -> None:
    _require(spec, "session_name", "entity_type", "source_path", "target_group_path")
    _require_write_confirmation(spec)
    session_name: str = spec["session_name"]
    entity_type: str = spec["entity_type"]
    source_path: list[str] = spec["source_path"]
    target_group_path: list[str] = spec["target_group_path"]
    _check_entity_type(entity_type)

    kp, database_path = _open_db_from_session(session_name)

    with DatabaseLock(database_path):
        backup_path = _make_backup(database_path)
        target_group = _resolve_group(kp, target_group_path)

        if entity_type == "entry":
            entry = kp.find_entries(path=source_path, first=True)
            if entry is None:
                raise ValueError(f"Entry not found at path: {source_path}")
            kp.move_entry(entry, target_group)
        else:
            group = kp.find_groups(path=source_path, first=True)
            if group is None:
                raise ValueError(f"Group not found at path: {source_path}")
            kp.move_group(group, target_group)

        kp.save()
        print(
            f"{entity_type.capitalize()} moved from {source_path} "
            f"to {target_group_path}.\n"
            f"Backup: {backup_path}"
        )


def cmd_edit_entity(spec: dict[str, Any]) -> None:
    _require(spec, "session_name", "entity_type", "source_path", "fields")
    _require_write_confirmation(spec)
    session_name: str = spec["session_name"]
    entity_type: str = spec["entity_type"]
    source_path: list[str] = spec["source_path"]
    fields: dict[str, Any] = spec["fields"]
    _check_entity_type(entity_type)

    if not isinstance(fields, dict) or not fields:
        raise ValueError("'fields' must be a non-empty object.")

    # Validate field names before touching the database
    if entity_type == "entry":
        unknown = set(fields.keys()) - ALLOWED_ENTRY_FIELDS
    else:
        unknown = set(fields.keys()) - ALLOWED_GROUP_FIELDS

    if unknown:
        raise ValueError(
            f"Unknown field(s) for {entity_type}: {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_ENTRY_FIELDS if entity_type == 'entry' else ALLOWED_GROUP_FIELDS)}"
        )

    kp, database_path = _open_db_from_session(session_name)

    with DatabaseLock(database_path):
        backup_path = _make_backup(database_path)

        if entity_type == "entry":
            entry = kp.find_entries(path=source_path, first=True)
            if entry is None:
                raise ValueError(f"Entry not found at path: {source_path}")
            if "title" in fields:
                entry.title = fields["title"]
            if "username" in fields:
                entry.username = fields["username"]
            if "url" in fields:
                entry.url = fields["url"]
            if "notes" in fields:
                entry.notes = fields["notes"]
            if fields.get("change_password"):
                new_pw = os.environ.get("KEEPASS_ENTRY_PASSWORD")
                if not new_pw:
                    raise ValueError(
                        "change_password is true but KEEPASS_ENTRY_PASSWORD "
                        "environment variable is not set."
                    )
                entry.password = new_pw
        else:
            group = kp.find_groups(path=source_path, first=True)
            if group is None:
                raise ValueError(f"Group not found at path: {source_path}")
            if "name" in fields:
                group.name = fields["name"]
            if "notes" in fields:
                group.notes = fields["notes"]

        kp.save()
        print(
            f"{entity_type.capitalize()} at {source_path} updated.\n"
            f"Fields changed: {list(fields.keys())}\n"
            f"Backup: {backup_path}"
        )


def cmd_search_entries(spec: dict[str, Any]) -> None:
    _require(spec, "session_name")
    session_name: str = spec["session_name"]
    search_term: str | None = spec.get("search_term")
    group_path: list[str] | None = spec.get("group_path")

    kp, _ = _open_db_from_session(session_name)

    results = []

    if group_path is not None:
        if not isinstance(group_path, list):
            raise ValueError("group_path must be a list of path segments.")
        _check_path_segments(group_path, "group_path")
        parent_group = _resolve_group(kp, group_path)
        entries = parent_group.entries
    else:
        entries = kp.entries

    for entry in entries:
        if search_term:
            search_lower = search_term.lower()
            match = (
                search_lower in (entry.title or "").lower()
                or search_lower in (entry.username or "").lower()
            )
            if not match:
                continue
        results.append(entry)

    if not results:
        print(f"No entries found matching query.")
        return

    print(f"Found {len(results)} entry(ies):")
    for i, entry in enumerate(results, 1):
        print(f"  {i}. Title: {entry.title}")
        if entry.username:
            print(f"     Username: {entry.username}")
        if entry.url:
            print(f"     URL: {entry.url}")


def cmd_show_entity(spec: dict[str, Any]) -> None:
    _require(spec, "session_name", "entity_type", "source_path")
    session_name: str = spec["session_name"]
    entity_type: str = spec["entity_type"]
    source_path: list[str] = spec["source_path"]
    _check_entity_type(entity_type)

    kp, _ = _open_db_from_session(session_name)

    if entity_type == "entry":
        entry = kp.find_entries(path=source_path, first=True)
        if entry is None:
            raise ValueError(f"Entry not found at path: {source_path}")
        print(f"Entry: {entry.title}")
        print(f"  Username: {entry.username or '(none)'}")
        print(f"  URL: {entry.url or '(none)'}")
        print(f"  Notes: {entry.notes or '(none)'}")
    else:
        group = kp.find_groups(path=source_path, first=True)
        if group is None:
            raise ValueError(f"Group not found at path: {source_path}")
        print(f"Group: {group.name}")
        print(f"  Notes: {group.notes or '(none)'}")
        print(f"  Entries: {len(group.entries)}")
        print(f"  Subgroups: {len(group.subgroups)}")


def cmd_forget(spec: dict[str, Any]) -> None:
    """Alias for cmd_close_database for better UX."""
    cmd_close_database(spec)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

SUBCOMMAND_HANDLERS = {
    "open-database": cmd_open_database,
    "close-database": cmd_close_database,
    "create-entity": cmd_create_entity,
    "move-entity": cmd_move_entity,
    "edit-entity": cmd_edit_entity,
    "search-entries": cmd_search_entries,
    "show-entity": cmd_show_entity,
    "forget": cmd_forget,
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="keepass_safe_ops",
        description=(
            "Safe, auditable KeePass operations helper. "
            "Allowlisted subcommands: "
            + ", ".join(sorted(ALLOWLISTED_SUBCOMMANDS))
        ),
    )
    parser.add_argument(
        "subcommand",
        choices=sorted(ALLOWLISTED_SUBCOMMANDS),
        help="Operation to perform.",
    )
    parser.add_argument(
        "--spec-file",
        required=True,
        metavar="PATH",
        help="Path to a JSON spec file describing the operation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    subcommand: str = args.subcommand

    # Extra guard: reject if the subcommand itself matches forbidden patterns
    # (redundant given argparse choices, but kept for defence in depth)
    if FORBIDDEN_SUBCOMMAND_PATTERNS.search(subcommand):
        print(
            f"ERROR: Subcommand '{subcommand}' resembles a delete-like operation "
            "and is not supported.",
            file=sys.stderr,
        )
        return 2

    try:
        spec = load_spec(args.spec_file)
        handler = SUBCOMMAND_HANDLERS[subcommand]
        handler(spec)
        return 0
    except (ImportError, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
