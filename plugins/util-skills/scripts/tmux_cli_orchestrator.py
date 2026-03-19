"""Manage delegated Copilot/OpenCode tasks in tmux-backed local sessions."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ALLOWLISTED_SUBCOMMANDS = {
    "repo-register",
    "repo-list",
    "repo-show",
    "session-create",
    "session-list",
    "session-attach",
    "status-show",
    "task-enqueue",
    "task-start-next",
    "task-list",
    "task-show",
    "task-cancel",
}
SUPPORTED_CLI_ADAPTERS = ("copilot", "opencode")
SUPPORTED_EXECUTION_MODES = ("queue", "worktree")
DEFAULT_STATE_ROOT = Path.home() / ".copilot-util-skills" / "tmux-orchestrator"
RUNNER_SESSION_PREFIX = "util"
DASHBOARD_WINDOW_NAME = "dashboard"
MAX_TITLE_LENGTH = 72


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(value: str, *, default: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or default


def shorten(text: str, *, limit: int) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def resolve_state_root(raw_path: str | None) -> Path:
    if raw_path:
        return Path(raw_path).expanduser().resolve()
    return DEFAULT_STATE_ROOT.resolve()


def run_command(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or "unknown command failure"
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")
    return completed


def detect_git_root(path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def normalize_repo_root(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {raw_path}")
    if not path.is_dir():
        raise ValueError(f"Repository path must be a directory: {raw_path}")
    git_root = detect_git_root(path)
    return git_root or path


def build_repo_id(repo_path: Path) -> str:
    digest = hashlib.sha1(str(repo_path).encode("utf-8")).hexdigest()[:8]
    return f"{slugify(repo_path.name, default='repo')}-{digest}"


def build_tmux_session_name(repo_id: str) -> str:
    return f"{RUNNER_SESSION_PREFIX}-{repo_id}"


def repo_state_dir(state_root: Path, repo_id: str) -> Path:
    return state_root / "repos" / repo_id


def repo_metadata_path(state_root: Path, repo_id: str) -> Path:
    return repo_state_dir(state_root, repo_id) / "repo.json"


def session_metadata_path(repo_dir: Path, session_id: str) -> Path:
    return repo_dir / "sessions" / f"{session_id}.json"


def task_metadata_path(repo_dir: Path, task_id: str) -> Path:
    return repo_dir / "tasks" / f"{task_id}.json"


def ensure_repo_dirs(repo_dir: Path) -> None:
    for child in ("sessions", "tasks", "logs", "prompts"):
        (repo_dir / child).mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def load_records(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        records.append(load_json(path))
    return records


class RepoLock:
    def __init__(self, repo_dir: Path) -> None:
        self.lock_path = repo_dir / "repo.lock"
        self.handle: Any | None = None

    def __enter__(self) -> "RepoLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, exc_tb: Any) -> None:
        if self.handle is None:
            return
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()
        self.handle = None


@contextmanager
def locked_repo_dir(state_root: Path, repo_id: str) -> Iterator[Path]:
    repo_dir = repo_state_dir(state_root, repo_id)
    ensure_repo_dirs(repo_dir)
    with RepoLock(repo_dir):
        yield repo_dir


def iter_registered_repos(state_root: Path) -> list[dict[str, Any]]:
    repos_root = state_root / "repos"
    if not repos_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for repo_path in sorted(repos_root.glob("*/repo.json")):
        record = load_json(repo_path)
        repo_dir = repo_path.parent
        sessions = load_records(repo_dir / "sessions")
        tasks = load_records(repo_dir / "tasks")
        record["session_count"] = len(sessions)
        record["task_counts"] = summarize_tasks(tasks)
        records.append(record)
    return records


def summarize_tasks(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
    for task in tasks:
        status = task.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def resolve_repo_record(
    state_root: Path,
    *,
    repo_root: str | None = None,
    repo_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    if repo_id:
        metadata_path = repo_metadata_path(state_root, repo_id)
        if not metadata_path.exists():
            raise FileNotFoundError(f"Unknown repo id: {repo_id}")
        return metadata_path.parent, load_json(metadata_path)

    if not repo_root:
        raise ValueError("Either --repo-root or --repo-id is required.")

    normalized = normalize_repo_root(repo_root)
    guessed_id = build_repo_id(normalized)
    metadata_path = repo_metadata_path(state_root, guessed_id)
    if not metadata_path.exists():
        raise FileNotFoundError(
            "Repository is not registered yet. Run repo-register first."
        )
    return metadata_path.parent, load_json(metadata_path)


def register_repo(
    state_root: Path,
    repo_root: str,
    *,
    purpose: str,
    alias: str | None,
    default_cli: str | None,
) -> dict[str, Any]:
    normalized_root = normalize_repo_root(repo_root)
    repo_id = build_repo_id(normalized_root)
    repo_dir = repo_state_dir(state_root, repo_id)
    ensure_repo_dirs(repo_dir)
    git_root = detect_git_root(normalized_root)
    metadata_path = repo_metadata_path(state_root, repo_id)
    now = utc_now()

    with RepoLock(repo_dir):
        record = load_json(metadata_path) if metadata_path.exists() else {
            "created_at": now,
            "repo_id": repo_id,
            "tmux_session_name": build_tmux_session_name(repo_id),
        }
        record.update(
            {
                "alias": alias or record.get("alias") or slugify(normalized_root.name, default="repo"),
                "default_cli": default_cli or record.get("default_cli") or "copilot",
                "git_root": str(git_root) if git_root else None,
                "last_used_at": now,
                "purpose": purpose,
                "repo_name": normalized_root.name,
                "repo_path": str(normalized_root),
                "worktree_root": str(state_root / "worktrees" / repo_id),
            }
        )
        write_json(metadata_path, record)
        sessions = load_records(repo_dir / "sessions")
        tasks = load_records(repo_dir / "tasks")

    return {
        "repo": record,
        "session_count": len(sessions),
        "task_counts": summarize_tasks(tasks),
    }


def build_idle_shell_command(message: str) -> str:
    script = (
        "printf '%s\\n' "
        + shlex.quote(message)
        + "; exec \"${SHELL:-/bin/bash}\" -l"
    )
    return f"bash -lc {shlex.quote(script)}"


def tmux_session_exists(tmux_bin: str, session_name: str) -> bool:
    result = subprocess.run(
        [tmux_bin, "has-session", "-t", session_name],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ensure_tmux_session(tmux_bin: str, session_name: str) -> None:
    if tmux_session_exists(tmux_bin, session_name):
        return
    run_command(
        [
            tmux_bin,
            "new-session",
            "-d",
            "-s",
            session_name,
            "-n",
            DASHBOARD_WINDOW_NAME,
            build_idle_shell_command("Delegated task dashboard ready."),
        ]
    )


def next_session_id(existing: list[dict[str, Any]], label: str | None) -> str:
    base = slugify(label or "session", default="session")
    candidate = base
    suffix = 2
    existing_ids = {item["session_id"] for item in existing}
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def list_tmux_panes(tmux_bin: str, session_name: str, window_name: str) -> list[str]:
    result = run_command(
        [tmux_bin, "list-panes", "-t", f"{session_name}:{window_name}", "-F", "#{pane_id}"],
    )
    panes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not panes:
        raise RuntimeError(f"No panes found for {session_name}:{window_name}")
    return panes


def session_attach_command(session_name: str) -> str:
    return f"tmux attach-session -t {shlex.quote(session_name)}"


def create_session(
    state_root: Path,
    repo_record: dict[str, Any],
    *,
    tmux_bin: str,
    label: str | None,
    default_cli: str | None,
) -> dict[str, Any]:
    shutil.which(tmux_bin) or (_ for _ in ()).throw(FileNotFoundError(f"tmux binary not found: {tmux_bin}"))
    repo_id = repo_record["repo_id"]
    repo_dir = repo_state_dir(state_root, repo_id)
    ensure_repo_dirs(repo_dir)
    now = utc_now()

    with RepoLock(repo_dir):
        current_repo = load_json(repo_metadata_path(state_root, repo_id))
        sessions = load_records(repo_dir / "sessions")
        session_id = next_session_id(sessions, label)
        session_name = current_repo["tmux_session_name"]
        ensure_tmux_session(tmux_bin, session_name)
        window_name = shorten(f"{session_id}", limit=MAX_TITLE_LENGTH)
        run_command(
            [
                tmux_bin,
                "new-window",
                "-d",
                "-t",
                session_name,
                "-n",
                window_name,
                build_idle_shell_command(f"Worker {session_id} is idle."),
            ]
        )
        run_command(
            [
                tmux_bin,
                "split-window",
                "-h",
                "-t",
                f"{session_name}:{window_name}",
                build_idle_shell_command("Session status pane ready."),
            ]
        )
        run_command([tmux_bin, "select-layout", "-t", f"{session_name}:{window_name}", "even-horizontal"])
        panes = list_tmux_panes(tmux_bin, session_name, window_name)

        session_record = {
            "active_task_id": None,
            "cli": default_cli or current_repo.get("default_cli") or "copilot",
            "created_at": now,
            "label": label or session_id,
            "last_used_at": now,
            "repo_id": repo_id,
            "runner_pane_id": panes[0],
            "session_id": session_id,
            "status": "idle",
            "status_pane_id": panes[-1],
            "tmux_session_name": session_name,
            "window_name": window_name,
        }
        write_json(session_metadata_path(repo_dir, session_id), session_record)
        current_repo["last_used_at"] = now
        write_json(repo_metadata_path(state_root, repo_id), current_repo)

    return {
        "repo": current_repo,
        "session": session_record,
        "attach_command": session_attach_command(session_name),
    }


def update_task_record(repo_dir: Path, task: dict[str, Any]) -> None:
    write_json(task_metadata_path(repo_dir, task["task_id"]), task)


def update_session_record(repo_dir: Path, session: dict[str, Any]) -> None:
    write_json(session_metadata_path(repo_dir, session["session_id"]), session)


def choose_idle_session(idle_sessions: list[dict[str, Any]], preferred_session_id: str | None) -> dict[str, Any] | None:
    if preferred_session_id:
        for session in idle_sessions:
            if session["session_id"] == preferred_session_id:
                return session
    return idle_sessions[0] if idle_sessions else None


def load_task(repo_dir: Path, task_id: str) -> dict[str, Any]:
    path = task_metadata_path(repo_dir, task_id)
    if not path.exists():
        raise FileNotFoundError(f"Unknown task id: {task_id}")
    return load_json(path)


def save_prompt_copy(repo_dir: Path, task_id: str, *, prompt_text: str, source_path: str | None = None) -> str:
    suffix = Path(source_path).suffix if source_path else ".md"
    if not suffix:
        suffix = ".md"
    prompt_path = repo_dir / "prompts" / f"{task_id}{suffix}"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt_text, encoding="utf-8")
    return str(prompt_path)


def create_task_record(
    repo_dir: Path,
    repo_record: dict[str, Any],
    *,
    cli: str,
    execution_mode: str,
    prompt_text: str,
    prompt_source_path: str | None,
    title: str | None,
    preferred_session_id: str | None,
    cleanup_prompt_file: bool,
    agent_name: str | None,
    model_name: str | None,
) -> dict[str, Any]:
    if cli not in SUPPORTED_CLI_ADAPTERS:
        raise ValueError(f"Unsupported CLI adapter: {cli}")
    if execution_mode not in SUPPORTED_EXECUTION_MODES:
        raise ValueError(f"Unsupported execution mode: {execution_mode}")
    task_id = uuid.uuid4().hex[:12]
    created_at = utc_now()
    prompt_file = save_prompt_copy(
        repo_dir,
        task_id,
        prompt_text=prompt_text,
        source_path=prompt_source_path,
    )
    derived_title = title or shorten(prompt_text.strip().splitlines()[0] if prompt_text.strip() else task_id, limit=MAX_TITLE_LENGTH)
    task = {
        "agent_name": agent_name,
        "cleanup_prompt_file": cleanup_prompt_file,
        "cli": cli,
        "created_at": created_at,
        "execution_mode": execution_mode,
        "finished_at": None,
        "log_file": None,
        "model_name": model_name,
        "preferred_session_id": preferred_session_id,
        "prompt_excerpt": shorten(prompt_text, limit=200),
        "prompt_file": prompt_file,
        "prompt_source_path": prompt_source_path,
        "repo_id": repo_record["repo_id"],
        "repo_path": repo_record["repo_path"],
        "session_id": None,
        "started_at": None,
        "status": "queued",
        "summary": None,
        "task_id": task_id,
        "title": derived_title,
        "updated_at": created_at,
        "window_name": None,
        "worktree_branch": None,
        "worktree_path": None,
    }
    update_task_record(repo_dir, task)
    return task


def build_worker_launch_command(task_file: Path, state_root: Path) -> str:
    worker_script = Path(__file__).resolve().with_name("tmux_cli_worker.py")
    command = shlex.join(
        [
            sys.executable,
            str(worker_script),
            "--task-file",
            str(task_file),
            "--state-root",
            str(state_root),
        ]
    )
    shell_script = (
        f"{command}; status=$?; "
        "printf '\\n[delegated worker exited with %s]\\n' \"$status\"; "
        "exec \"${SHELL:-/bin/bash}\" -l"
    )
    return f"bash -lc {shlex.quote(shell_script)}"


def tail_command(log_file: Path, task_title: str) -> str:
    script = (
        f"touch {shlex.quote(str(log_file))}; "
        f"printf '%s\\n' {shlex.quote(f'Tailing log for: {task_title}')}; "
        f"tail -n 200 -f {shlex.quote(str(log_file))}"
    )
    return f"bash -lc {shlex.quote(script)}"


def display_tmux_message(tmux_bin: str, session_name: str, message: str) -> None:
    subprocess.run(
        [tmux_bin, "display-message", "-t", session_name, message],
        check=False,
        capture_output=True,
        text=True,
    )


def rename_tmux_window(tmux_bin: str, session_name: str, window_name: str, new_name: str) -> None:
    subprocess.run(
        [tmux_bin, "rename-window", "-t", f"{session_name}:{window_name}", new_name],
        check=False,
        capture_output=True,
        text=True,
    )


def send_task_to_panes(
    tmux_bin: str,
    *,
    session_record: dict[str, Any],
    task: dict[str, Any],
    state_root: Path,
) -> None:
    session_name = session_record["tmux_session_name"]
    runner_target = session_record["runner_pane_id"]
    status_target = session_record["status_pane_id"]
    log_file = Path(task["log_file"])

    subprocess.run([tmux_bin, "send-keys", "-t", status_target, "C-c"], check=False, capture_output=True, text=True)
    subprocess.run([tmux_bin, "send-keys", "-t", runner_target, "C-c"], check=False, capture_output=True, text=True)
    subprocess.run([tmux_bin, "send-keys", "-t", status_target, tail_command(log_file, task["title"]), "C-m"], check=False, capture_output=True, text=True)
    subprocess.run(
        [
            tmux_bin,
            "send-keys",
            "-t",
            runner_target,
            build_worker_launch_command(task_metadata_path(repo_state_dir(state_root, task["repo_id"]), task["task_id"]), state_root),
            "C-m",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    display_tmux_message(tmux_bin, session_name, f"Started delegated task {task['task_id']} on {session_record['session_id']}")


def start_task(
    state_root: Path,
    repo_record: dict[str, Any],
    *,
    task: dict[str, Any],
    session: dict[str, Any],
    tmux_bin: str,
) -> dict[str, Any]:
    repo_dir = repo_state_dir(state_root, repo_record["repo_id"])
    now = utc_now()
    log_file = repo_dir / "logs" / f"{task['task_id']}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.touch(exist_ok=True)

    task["log_file"] = str(log_file)
    task["session_id"] = session["session_id"]
    task["started_at"] = now
    task["status"] = "running"
    task["updated_at"] = now
    task["window_name"] = session["window_name"]

    session["active_task_id"] = task["task_id"]
    session["last_used_at"] = now
    session["status"] = "busy"

    update_task_record(repo_dir, task)
    update_session_record(repo_dir, session)
    send_task_to_panes(tmux_bin, session_record=session, task=task, state_root=state_root)
    return task


def task_sort_key(task: dict[str, Any]) -> tuple[str, str]:
    return (task.get("created_at") or "", task.get("task_id") or "")


def start_eligible_tasks(
    state_root: Path,
    repo_record: dict[str, Any],
    *,
    tmux_bin: str,
) -> dict[str, Any]:
    repo_id = repo_record["repo_id"]
    repo_dir = repo_state_dir(state_root, repo_id)
    started: list[str] = []

    with RepoLock(repo_dir):
        current_repo = load_json(repo_metadata_path(state_root, repo_id))
        tasks = sorted(load_records(repo_dir / "tasks"), key=task_sort_key)
        sessions = sorted(load_records(repo_dir / "sessions"), key=lambda item: item["session_id"])
        idle_sessions = [item for item in sessions if item.get("status") != "busy"]
        active_queue = any(
            task.get("status") == "running" and task.get("execution_mode") == "queue"
            for task in tasks
        )

        for task in tasks:
            if task.get("status") != "queued":
                continue
            if not idle_sessions:
                break
            if task.get("execution_mode") == "queue" and active_queue:
                continue
            chosen = choose_idle_session(idle_sessions, task.get("preferred_session_id"))
            if not chosen:
                break
            start_task(state_root, current_repo, task=task, session=chosen, tmux_bin=tmux_bin)
            started.append(task["task_id"])
            idle_sessions = [item for item in idle_sessions if item["session_id"] != chosen["session_id"]]
            if task.get("execution_mode") == "queue":
                active_queue = True

    return {
        "repo_id": repo_id,
        "started_task_ids": started,
        "remaining_queued": summarize_tasks(load_records(repo_dir / "tasks")).get("queued", 0),
    }


def enqueue_task(
    state_root: Path,
    repo_record: dict[str, Any],
    *,
    cli: str,
    execution_mode: str,
    prompt_text: str,
    prompt_source_path: str | None,
    title: str | None,
    session_id: str | None,
    cleanup_prompt_file: bool,
    agent_name: str | None,
    model_name: str | None,
    tmux_bin: str,
) -> dict[str, Any]:
    if execution_mode == "worktree" and not repo_record.get("git_root"):
        raise ValueError("Worktree mode requires the target repository to be a git repository.")

    repo_dir = repo_state_dir(state_root, repo_record["repo_id"])
    ensure_repo_dirs(repo_dir)
    current_repo = load_json(repo_metadata_path(state_root, repo_record["repo_id"]))
    if not load_records(repo_dir / "sessions"):
        create_session(
            state_root,
            current_repo,
            tmux_bin=tmux_bin,
            label=session_id or "main",
            default_cli=cli,
        )

    with RepoLock(repo_dir):
        current_repo = load_json(repo_metadata_path(state_root, repo_record["repo_id"]))
        task = create_task_record(
            repo_dir,
            current_repo,
            cli=cli,
            execution_mode=execution_mode,
            prompt_text=prompt_text,
            prompt_source_path=prompt_source_path,
            title=title,
            preferred_session_id=session_id,
            cleanup_prompt_file=cleanup_prompt_file,
            agent_name=agent_name,
            model_name=model_name,
        )

    scheduling = start_eligible_tasks(state_root, repo_record, tmux_bin=tmux_bin)
    current_task = load_task(repo_dir, task["task_id"])
    return {"task": current_task, "scheduling": scheduling}


def repo_status(repo_dir: Path, repo_record: dict[str, Any]) -> dict[str, Any]:
    sessions = sorted(load_records(repo_dir / "sessions"), key=lambda item: item["session_id"])
    tasks = sorted(load_records(repo_dir / "tasks"), key=task_sort_key)
    active = [task for task in tasks if task.get("status") == "running"]
    queued = [task for task in tasks if task.get("status") == "queued"]
    return {
        "repo": repo_record,
        "sessions": sessions,
        "task_counts": summarize_tasks(tasks),
        "active_tasks": active,
        "queued_tasks": queued,
    }


def cancel_task(state_root: Path, repo_record: dict[str, Any], task_id: str) -> dict[str, Any]:
    repo_dir = repo_state_dir(state_root, repo_record["repo_id"])
    with RepoLock(repo_dir):
        task = load_task(repo_dir, task_id)
        if task.get("status") == "running":
            raise ValueError(
                "Running task cancellation is not supported automatically. Interrupt the tmux pane manually if needed."
            )
        if task.get("status") != "queued":
            raise ValueError(f"Only queued tasks can be cancelled, got status {task.get('status')!r}.")
        task["status"] = "cancelled"
        task["finished_at"] = utc_now()
        task["summary"] = "Cancelled before execution."
        task["updated_at"] = task["finished_at"]
        update_task_record(repo_dir, task)
    return {"task": task}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tmux_cli_orchestrator",
        description=(
            "Manage delegated Copilot/OpenCode work in tmux-backed local sessions. "
            "Allowlisted subcommands: " + ", ".join(sorted(ALLOWLISTED_SUBCOMMANDS))
        ),
    )
    parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT), help="Directory used to persist repo/session/task state.")
    parser.add_argument("--tmux-bin", default="tmux", help="tmux executable to use.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    repo_register = subparsers.add_parser("repo-register", help="Register or update repo memory for delegated sessions.")
    repo_register.add_argument("--repo-root", required=True)
    repo_register.add_argument("--purpose", required=True)
    repo_register.add_argument("--alias")
    repo_register.add_argument("--default-cli", choices=SUPPORTED_CLI_ADAPTERS)

    subparsers.add_parser("repo-list", help="List registered repositories.")

    repo_show = subparsers.add_parser("repo-show", help="Show a registered repository.")
    repo_group = repo_show.add_mutually_exclusive_group(required=True)
    repo_group.add_argument("--repo-root")
    repo_group.add_argument("--repo-id")

    session_create = subparsers.add_parser("session-create", help="Create a managed tmux worker session.")
    session_group = session_create.add_mutually_exclusive_group(required=True)
    session_group.add_argument("--repo-root")
    session_group.add_argument("--repo-id")
    session_create.add_argument("--label")
    session_create.add_argument("--cli", choices=SUPPORTED_CLI_ADAPTERS)

    session_list = subparsers.add_parser("session-list", help="List worker sessions for a repository.")
    session_list_group = session_list.add_mutually_exclusive_group(required=True)
    session_list_group.add_argument("--repo-root")
    session_list_group.add_argument("--repo-id")

    session_attach = subparsers.add_parser("session-attach", help="Return the tmux attach command for a repository.")
    session_attach_group = session_attach.add_mutually_exclusive_group(required=True)
    session_attach_group.add_argument("--repo-root")
    session_attach_group.add_argument("--repo-id")

    status_show = subparsers.add_parser("status-show", help="Show repo/session/task status summary.")
    status_group = status_show.add_mutually_exclusive_group(required=True)
    status_group.add_argument("--repo-root")
    status_group.add_argument("--repo-id")

    task_enqueue = subparsers.add_parser("task-enqueue", help="Queue or start a delegated task.")
    task_enqueue_group = task_enqueue.add_mutually_exclusive_group(required=True)
    task_enqueue_group.add_argument("--repo-root")
    task_enqueue_group.add_argument("--repo-id")
    prompt_group = task_enqueue.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file")
    task_enqueue.add_argument("--title")
    task_enqueue.add_argument("--cli", choices=SUPPORTED_CLI_ADAPTERS)
    task_enqueue.add_argument("--session-id")
    task_enqueue.add_argument("--execution-mode", choices=SUPPORTED_EXECUTION_MODES, default="queue")
    task_enqueue.add_argument("--agent")
    task_enqueue.add_argument("--model")
    task_enqueue.add_argument("--keep-prompt-file", action="store_true")

    task_start_next = subparsers.add_parser("task-start-next", help="Start any queued task that is eligible to run.")
    task_start_group = task_start_next.add_mutually_exclusive_group(required=True)
    task_start_group.add_argument("--repo-root")
    task_start_group.add_argument("--repo-id")

    task_list = subparsers.add_parser("task-list", help="List tasks for a repository.")
    task_list_group = task_list.add_mutually_exclusive_group(required=True)
    task_list_group.add_argument("--repo-root")
    task_list_group.add_argument("--repo-id")

    task_show = subparsers.add_parser("task-show", help="Show a single delegated task.")
    task_show_group = task_show.add_mutually_exclusive_group(required=True)
    task_show_group.add_argument("--repo-root")
    task_show_group.add_argument("--repo-id")
    task_show.add_argument("--task-id", required=True)

    task_cancel = subparsers.add_parser("task-cancel", help="Cancel a queued delegated task.")
    task_cancel_group = task_cancel.add_mutually_exclusive_group(required=True)
    task_cancel_group.add_argument("--repo-root")
    task_cancel_group.add_argument("--repo-id")
    task_cancel.add_argument("--task-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state_root = resolve_state_root(args.state_root)
    state_root.mkdir(parents=True, exist_ok=True)

    try:
        if args.subcommand == "repo-register":
            result = register_repo(
                state_root,
                args.repo_root,
                purpose=args.purpose,
                alias=args.alias,
                default_cli=args.default_cli,
            )
        elif args.subcommand == "repo-list":
            result = {"repos": iter_registered_repos(state_root)}
        else:
            repo_dir, repo_record = resolve_repo_record(
                state_root,
                repo_root=getattr(args, "repo_root", None),
                repo_id=getattr(args, "repo_id", None),
            )
            if args.subcommand == "repo-show":
                result = repo_status(repo_dir, repo_record)
            elif args.subcommand == "session-create":
                result = create_session(
                    state_root,
                    repo_record,
                    tmux_bin=args.tmux_bin,
                    label=args.label,
                    default_cli=args.cli,
                )
            elif args.subcommand == "session-list":
                result = {"repo": repo_record, "sessions": load_records(repo_dir / "sessions")}
            elif args.subcommand == "session-attach":
                result = {
                    "repo": repo_record,
                    "tmux_session_name": repo_record["tmux_session_name"],
                    "attach_command": session_attach_command(repo_record["tmux_session_name"]),
                }
            elif args.subcommand == "status-show":
                result = repo_status(repo_dir, repo_record)
            elif args.subcommand == "task-enqueue":
                if args.prompt_file:
                    prompt_source = Path(args.prompt_file).expanduser().resolve()
                    prompt_text = prompt_source.read_text(encoding="utf-8")
                    prompt_source_path = str(prompt_source)
                else:
                    prompt_text = args.prompt
                    prompt_source_path = None
                cli = args.cli or repo_record.get("default_cli") or "copilot"
                result = enqueue_task(
                    state_root,
                    repo_record,
                    cli=cli,
                    execution_mode=args.execution_mode,
                    prompt_text=prompt_text,
                    prompt_source_path=prompt_source_path,
                    title=args.title,
                    session_id=args.session_id,
                    cleanup_prompt_file=not args.keep_prompt_file,
                    agent_name=args.agent,
                    model_name=args.model,
                    tmux_bin=args.tmux_bin,
                )
            elif args.subcommand == "task-start-next":
                result = start_eligible_tasks(state_root, repo_record, tmux_bin=args.tmux_bin)
            elif args.subcommand == "task-list":
                result = {"repo": repo_record, "tasks": sorted(load_records(repo_dir / "tasks"), key=task_sort_key)}
            elif args.subcommand == "task-show":
                result = {"task": load_task(repo_dir, args.task_id)}
            elif args.subcommand == "task-cancel":
                result = cancel_task(state_root, repo_record, args.task_id)
            else:
                parser.error(f"Unsupported subcommand: {args.subcommand}")
                return 2

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
