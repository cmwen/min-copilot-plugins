#!/usr/bin/env python3

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".copilot" / "logseq" / "logseq.sqlite3"
DB_PATH_ENV = "LOGSEQ_SQLITE_PATH"
VAULT_ROOT_ENV = "LOGSEQ_VAULT_ROOT"

BLOCK_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d+[.)])\s+(?P<text>.+)$")
PROPERTY_RE = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z0-9 _/-]*)::\s*(?P<value>.+)$")
H1_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")
PAGE_REF_RE = re.compile(r"\[\[([^\]]+)\]\]")
BLOCK_REF_RE = re.compile(r"\(\(([A-Za-z0-9_-]+)\)\)")
TASK_RE = re.compile(
    r"^(?P<state>TODO|DOING|DONE|WAITING|NOW|LATER|CANCELED|CANCELLED)\b(?:\s+(?P<body>.*))?$",
    re.IGNORECASE,
)


@dataclasses.dataclass
class ParsedBlock:
    line_no: int
    parent_line_no: int | None
    indent: int
    marker: str
    text: str
    task_state: str | None
    properties: dict[str, str]
    tags: list[str]
    page_refs: list[str]
    block_refs: list[str]


@dataclasses.dataclass
class ParsedPage:
    page_name: str
    title: str
    file_path: Path
    content_hash: str
    mtime: float
    properties: dict[str, str]
    blocks: list[ParsedBlock]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Index Logseq markdown into SQLite.")
    parser.add_argument(
        "--db-path",
        help="Path to the SQLite database. Defaults to LOGSEQ_SQLITE_PATH or a user-local path.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Index all markdown files under a vault root.")
    sync_parser.add_argument("--vault-root", help="Path to the Logseq vault root.")
    sync_parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove rows for files that are no longer present under the vault root.",
    )

    sync_file_parser = subparsers.add_parser("sync-file", help="Index one Logseq markdown file.")
    sync_file_parser.add_argument("file_path", help="Path to a Logseq markdown file.")

    search_parser = subparsers.add_parser("search", help="Search indexed pages and blocks.")
    search_parser.add_argument("query", help="Search terms for the SQLite index.")
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum number of matches to return.")

    show_parser = subparsers.add_parser("show-page", help="Show one page and its indexed blocks.")
    show_parser.add_argument("page_name", help="Logseq page name to inspect.")

    subparsers.add_parser("stats", help="Show index counts.")
    return parser.parse_args()


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_value = os.getenv(DB_PATH_ENV)
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DB_PATH.expanduser()


def resolve_vault_root(explicit: str | None) -> Path:
    candidate = explicit or os.getenv(VAULT_ROOT_ENV)
    if not candidate:
        raise SystemExit(
            f"Missing vault root. Pass --vault-root or set {VAULT_ROOT_ENV}."
        )
    return Path(candidate).expanduser()


def connect_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            page_name TEXT PRIMARY KEY,
            file_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            mtime REAL NOT NULL,
            indexed_at TEXT NOT NULL,
            properties_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_name TEXT NOT NULL REFERENCES pages(page_name) ON DELETE CASCADE,
            file_path TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            parent_line_no INTEGER,
            indent INTEGER NOT NULL,
            marker TEXT NOT NULL,
            text TEXT NOT NULL,
            task_state TEXT,
            properties_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            page_refs_json TEXT NOT NULL,
            block_refs_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_blocks_page_name ON blocks(page_name);
        CREATE INDEX IF NOT EXISTS idx_blocks_file_path ON blocks(file_path);
        CREATE INDEX IF NOT EXISTS idx_blocks_line_no ON blocks(file_path, line_no);

        CREATE VIRTUAL TABLE IF NOT EXISTS blocks_fts USING fts5(
            page_name,
            text,
            tags,
            refs,
            properties,
            tokenize = 'unicode61'
        );
        """
    )


def normalize_indent(indent: str) -> int:
    return len(indent.replace("\t", "    "))


def extract_entities(text: str) -> tuple[list[str], list[str], list[str]]:
    tags = sorted({match.group(1) for match in TAG_RE.finditer(text)})
    page_refs = sorted({match.group(1).strip() for match in PAGE_REF_RE.finditer(text)})
    block_refs = sorted({match.group(1).strip() for match in BLOCK_REF_RE.finditer(text)})
    return tags, page_refs, block_refs


def extract_task_state(text: str) -> str | None:
    match = TASK_RE.match(text)
    if not match:
        return None
    return match.group("state").upper()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_logseq_markdown(file_path: Path) -> ParsedPage:
    text = file_path.read_text(encoding="utf-8")
    page_name = file_path.stem
    title = page_name
    page_properties: dict[str, str] = {}
    blocks: list[ParsedBlock] = []
    stack: list[ParsedBlock] = []
    in_code_fence = False

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        fence = FENCE_RE.match(raw_line)
        if fence:
            in_code_fence = not in_code_fence
            stack.clear()
            continue

        if in_code_fence or not stripped:
            continue

        heading = H1_RE.match(raw_line)
        if heading and title == page_name:
            title = heading.group("title").strip()
            stack.clear()
            continue

        property_match = PROPERTY_RE.match(raw_line)
        if property_match:
            key = property_match.group("key").strip()
            value = property_match.group("value").strip()
            target = stack[-1].properties if stack else page_properties
            target[key] = value
            continue

        block_match = BLOCK_RE.match(raw_line)
        if block_match:
            indent = normalize_indent(block_match.group("indent"))
            while stack and indent <= stack[-1].indent:
                stack.pop()
            parent_line_no = stack[-1].line_no if stack else None
            text_value = block_match.group("text").strip()
            tags, page_refs, block_refs = extract_entities(text_value)
            block = ParsedBlock(
                line_no=line_no,
                parent_line_no=parent_line_no,
                indent=indent,
                marker=block_match.group("marker"),
                text=text_value,
                task_state=extract_task_state(text_value),
                properties={},
                tags=tags,
                page_refs=page_refs,
                block_refs=block_refs,
            )
            blocks.append(block)
            stack.append(block)
            continue

        stack.clear()
        text_value = stripped
        tags, page_refs, block_refs = extract_entities(text_value)
        block = ParsedBlock(
            line_no=line_no,
            parent_line_no=None,
            indent=0,
            marker="paragraph",
            text=text_value,
            task_state=extract_task_state(text_value),
            properties={},
            tags=tags,
            page_refs=page_refs,
            block_refs=block_refs,
        )
        blocks.append(block)

    return ParsedPage(
        page_name=page_name,
        title=title,
        file_path=file_path,
        content_hash=hash_text(text),
        mtime=file_path.stat().st_mtime,
        properties=page_properties,
        blocks=blocks,
    )


def is_hidden_path(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def iter_markdown_files(vault_root: Path) -> list[Path]:
    return sorted(
        path
        for path in vault_root.rglob("*.md")
        if path.is_file() and not is_hidden_path(path, vault_root)
    )


def delete_file_index(conn: sqlite3.Connection, file_path: Path | str) -> None:
    file_path_str = str(Path(file_path).resolve())
    block_ids = [row["id"] for row in conn.execute("SELECT id FROM blocks WHERE file_path = ?", (file_path_str,))]
    for block_id in block_ids:
        conn.execute("DELETE FROM blocks_fts WHERE rowid = ?", (block_id,))
    conn.execute("DELETE FROM blocks WHERE file_path = ?", (file_path_str,))
    conn.execute("DELETE FROM pages WHERE file_path = ?", (file_path_str,))


def upsert_page(conn: sqlite3.Connection, page: ParsedPage) -> None:
    conn.execute(
        """
        INSERT INTO pages (
            page_name, file_path, title, content_hash, mtime, indexed_at, properties_json
        ) VALUES (?, ?, ?, ?, ?, datetime('now'), ?)
        ON CONFLICT(page_name) DO UPDATE SET
            file_path = excluded.file_path,
            title = excluded.title,
            content_hash = excluded.content_hash,
            mtime = excluded.mtime,
            indexed_at = excluded.indexed_at,
            properties_json = excluded.properties_json
        """,
        (
            page.page_name,
            str(page.file_path.resolve()),
            page.title,
            page.content_hash,
            page.mtime,
            json.dumps(page.properties, ensure_ascii=False, sort_keys=True),
        ),
    )


def insert_blocks(conn: sqlite3.Connection, page: ParsedPage) -> int:
    inserted = 0
    file_path = str(page.file_path.resolve())
    for block in page.blocks:
        cursor = conn.execute(
            """
            INSERT INTO blocks (
                page_name, file_path, line_no, parent_line_no, indent, marker,
                text, task_state, properties_json, tags_json, page_refs_json, block_refs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page.page_name,
                file_path,
                block.line_no,
                block.parent_line_no,
                block.indent,
                block.marker,
                block.text,
                block.task_state,
                json.dumps(block.properties, ensure_ascii=False, sort_keys=True),
                json.dumps(block.tags, ensure_ascii=False),
                json.dumps(block.page_refs, ensure_ascii=False),
                json.dumps(block.block_refs, ensure_ascii=False),
            ),
        )
        block_id = cursor.lastrowid
        refs = sorted({*block.page_refs, *block.block_refs})
        conn.execute(
            """
            INSERT INTO blocks_fts (rowid, page_name, text, tags, refs, properties)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                block_id,
                page.page_name,
                block.text,
                " ".join(block.tags),
                " ".join(refs),
                " ".join(sorted(block.properties.keys())),
            ),
        )
        inserted += 1
    return inserted


def sync_parsed_page(conn: sqlite3.Connection, page: ParsedPage) -> dict[str, int]:
    existing = conn.execute(
        "SELECT content_hash, file_path FROM pages WHERE page_name = ?",
        (page.page_name,),
    ).fetchone()
    if (
        existing
        and existing["content_hash"] == page.content_hash
        and existing["file_path"] == str(page.file_path.resolve())
    ):
        return {"indexed": 0, "skipped": 1, "pruned": 0}

    delete_file_index(conn, page.file_path)
    upsert_page(conn, page)
    inserted = insert_blocks(conn, page)
    return {"indexed": inserted, "skipped": 0, "pruned": 0}


def sync_file(conn: sqlite3.Connection, file_path: Path) -> dict[str, int]:
    parsed = parse_logseq_markdown(file_path)
    return sync_parsed_page(conn, parsed)


def sync_vault(conn: sqlite3.Connection, vault_root: Path, prune: bool) -> dict[str, int]:
    files = iter_markdown_files(vault_root)
    file_paths = {str(path.resolve()) for path in files}
    totals = {"indexed": 0, "skipped": 0, "pruned": 0}

    conn.execute("BEGIN")
    try:
        for file_path in files:
            parsed = parse_logseq_markdown(file_path)
            result = sync_parsed_page(conn, parsed)
            for key, value in result.items():
                totals[key] += value

        if prune:
            stale_rows = conn.execute("SELECT file_path FROM pages").fetchall()
            stale_paths = [row["file_path"] for row in stale_rows if row["file_path"] not in file_paths]
            for stale_path in stale_paths:
                delete_file_index(conn, stale_path)
            totals["pruned"] = len(stale_paths)

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return totals


def search_index(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    sql = """
        SELECT
            p.page_name,
            p.title,
            b.line_no,
            b.parent_line_no,
            b.marker,
            b.text,
            b.task_state,
            snippet(blocks_fts, 1, '[', ']', '…', 16) AS snippet
        FROM blocks_fts
        JOIN blocks AS b ON b.id = blocks_fts.rowid
        JOIN pages AS p ON p.page_name = b.page_name
        WHERE blocks_fts MATCH ?
        ORDER BY bm25(blocks_fts)
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        pattern = f"%{query}%"
        fallback_sql = """
            SELECT
                p.page_name,
                p.title,
                b.line_no,
                b.parent_line_no,
                b.marker,
                b.text,
                b.task_state,
                b.text AS snippet
            FROM blocks AS b
            JOIN pages AS p ON p.page_name = b.page_name
            WHERE b.text LIKE ? OR p.page_name LIKE ? OR p.title LIKE ?
            ORDER BY p.page_name, b.line_no
            LIMIT ?
        """
        rows = conn.execute(fallback_sql, (pattern, pattern, pattern, limit)).fetchall()
    return [dict(row) for row in rows]


def show_page(conn: sqlite3.Connection, page_name: str) -> dict[str, Any]:
    page = conn.execute("SELECT * FROM pages WHERE page_name = ?", (page_name,)).fetchone()
    if page is None:
        raise SystemExit(f"No indexed page named '{page_name}' was found.")
    blocks = conn.execute(
        """
        SELECT *
        FROM blocks
        WHERE page_name = ?
        ORDER BY line_no, id
        """,
        (page_name,),
    ).fetchall()
    return {
        "page": dict(page),
        "blocks": [dict(row) for row in blocks],
    }


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    pages = conn.execute("SELECT COUNT(*) AS count FROM pages").fetchone()["count"]
    blocks = conn.execute("SELECT COUNT(*) AS count FROM blocks").fetchone()["count"]
    return {"pages": pages, "blocks": blocks}


def print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


def main() -> None:
    args = parse_args()
    db_path = resolve_db_path(args.db_path)
    conn = connect_database(db_path)

    try:
        if args.command == "sync":
            vault_root = resolve_vault_root(args.vault_root)
            result = sync_vault(conn, vault_root, args.prune)
            print_json(
                {
                    "database": str(db_path),
                    "vault_root": str(vault_root),
                    "result": result,
                }
            )
            return

        if args.command == "sync-file":
            file_path = Path(args.file_path).expanduser().resolve()
            result = sync_file(conn, file_path)
            print_json({"database": str(db_path), "file_path": str(file_path), "result": result})
            return

        if args.command == "search":
            rows = search_index(conn, args.query, args.limit)
            print_json({"database": str(db_path), "query": args.query, "results": rows})
            return

        if args.command == "show-page":
            payload = show_page(conn, args.page_name)
            payload["database"] = str(db_path)
            print_json(payload)
            return

        if args.command == "stats":
            print_json({"database": str(db_path), "stats": stats(conn)})
            return

        raise SystemExit(f"Unknown command: {args.command}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
