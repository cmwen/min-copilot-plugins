"""Run one delegated Copilot/OpenCode task and update tmux/session state."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import tmux_cli_orchestrator as orchestrator


SUPPORTED_CLI_ADAPTERS = orchestrator.SUPPORTED_CLI_ADAPTERS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_task(task_file: Path) -> dict[str, Any]:
    return orchestrator.load_json(task_file)


def read_prompt(prompt_file: Path) -> str:
    text = prompt_file.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Prompt file is empty.")
    return text


def summarize_result(exit_code: int, cli: str, cwd: Path, started_at: str) -> str:
    return (
        f"Delegated {cli} task exited with code {exit_code} in {cwd} "
        f"(started {started_at})."
    )


def build_cli_command(
    *,
    cli: str,
    prompt_text: str,
    cwd: Path,
    agent_name: str | None,
    model_name: str | None,
) -> list[str]:
    if cli == "copilot":
        command = [
            "copilot",
            "--allow-all-tools",
            "--add-dir",
            str(cwd),
            "--no-ask-user",
            "--output-format",
            "text",
            "-s",
        ]
        if agent_name:
            command.extend(["--agent", agent_name])
        if model_name:
            command.extend(["--model", model_name])
        command.extend(["--prompt", prompt_text])
        return command
    if cli == "opencode":
        command = ["opencode", "run", "--dir", str(cwd), "--format", "default"]
        if agent_name:
            command.extend(["--agent", agent_name])
        if model_name:
            command.extend(["--model", model_name])
        command.append(prompt_text)
        return command
    raise ValueError(f"Unsupported CLI adapter: {cli}")


def send_best_effort_notification(title: str, message: str) -> str | None:
    if shutil.which("osascript"):
        script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
        result = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return "osascript"
    if shutil.which("notify-send"):
        result = subprocess.run(["notify-send", title, message], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return "notify-send"
    return None


def prepare_worktree(task: dict[str, Any], repo_record: dict[str, Any], state_root: Path) -> tuple[Path, str | None, str | None]:
    repo_root = Path(repo_record["repo_path"])
    if task.get("execution_mode") != "worktree":
        return repo_root, None, None

    git_root_value = repo_record.get("git_root")
    if not git_root_value:
        raise ValueError("Task requested worktree execution, but the repository is not a git repository.")

    git_root = Path(git_root_value)
    worktree_root = Path(repo_record["worktree_root"]).expanduser().resolve()
    worktree_path = worktree_root / task["task_id"]
    branch_name = f"delegated-{task['task_id']}"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    orchestrator.run_command(
        [
            "git",
            "-C",
            str(git_root),
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            "HEAD",
        ]
    )
    return worktree_path, str(worktree_path), branch_name


def stream_command(command: list[str], *, cwd: Path, log_file: Path) -> int:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    with log_file.open("a", encoding="utf-8") as handle:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            handle.write(line)
        return process.wait()


def finalize_task(
    *,
    state_root: Path,
    repo_record: dict[str, Any],
    task: dict[str, Any],
    session_record: dict[str, Any],
    exit_code: int,
    summary: str,
    notification_title: str,
) -> dict[str, Any]:
    repo_dir = orchestrator.repo_state_dir(state_root, repo_record["repo_id"])
    finished_at = utc_now()
    notification_method = send_best_effort_notification(notification_title, summary)

    with orchestrator.RepoLock(repo_dir):
        latest_task = orchestrator.load_task(repo_dir, task["task_id"])
        latest_session = orchestrator.load_json(orchestrator.session_metadata_path(repo_dir, session_record["session_id"]))
        latest_task["finished_at"] = finished_at
        latest_task["status"] = "completed" if exit_code == 0 else "failed"
        latest_task["summary"] = summary
        latest_task["updated_at"] = finished_at
        latest_task["exit_code"] = exit_code
        latest_task["notification_method"] = notification_method
        if latest_task.get("cleanup_prompt_file") and exit_code == 0 and latest_task.get("prompt_file"):
            prompt_path = Path(latest_task["prompt_file"])
            if prompt_path.exists():
                prompt_path.unlink()
            latest_task["prompt_file"] = None
        orchestrator.update_task_record(repo_dir, latest_task)

        latest_session["active_task_id"] = None
        latest_session["last_used_at"] = finished_at
        latest_session["status"] = "idle"
        orchestrator.update_session_record(repo_dir, latest_session)

    tmux_bin = shutil.which("tmux") or "tmux"
    status_label = "done" if exit_code == 0 else "fail"
    orchestrator.display_tmux_message(
        tmux_bin,
        latest_session["tmux_session_name"],
        f"Task {latest_task['task_id']} {status_label}: {latest_task['title']}",
    )
    return latest_task


def run_task(task_file: Path, state_root: Path) -> dict[str, Any]:
    task = read_task(task_file)
    repo_dir = orchestrator.repo_state_dir(state_root, task["repo_id"])
    repo_record = orchestrator.load_json(orchestrator.repo_metadata_path(state_root, task["repo_id"]))
    session_record = orchestrator.load_json(orchestrator.session_metadata_path(repo_dir, task["session_id"]))

    prompt_path_value = task.get("prompt_file")
    if not prompt_path_value:
        raise ValueError("Task is missing a prompt file.")
    prompt_path = Path(prompt_path_value)
    prompt_text = read_prompt(prompt_path)
    log_file_value = task.get("log_file")
    if not log_file_value:
        raise ValueError("Task is missing a log file path.")
    log_file = Path(log_file_value)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cwd, worktree_path, branch_name = prepare_worktree(task, repo_record, state_root)
    if worktree_path:
        with orchestrator.RepoLock(repo_dir):
            latest_task = orchestrator.load_task(repo_dir, task["task_id"])
            latest_task["worktree_branch"] = branch_name
            latest_task["worktree_path"] = worktree_path
            latest_task["updated_at"] = utc_now()
            orchestrator.update_task_record(repo_dir, latest_task)
            task = latest_task

    if not shutil.which(task["cli"]):
        raise FileNotFoundError(f"CLI adapter binary not found on PATH: {task['cli']}")

    command = build_cli_command(
        cli=task["cli"],
        prompt_text=prompt_text,
        cwd=cwd,
        agent_name=task.get("agent_name"),
        model_name=task.get("model_name"),
    )
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] Starting delegated task {task['task_id']} in {cwd}\n")
        handle.write(f"[{utc_now()}] Adapter: {task['cli']}\n")

    exit_code = stream_command(command, cwd=cwd, log_file=log_file)
    summary = summarize_result(exit_code, task["cli"], cwd, task.get("started_at") or "unknown time")
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_now()}] {summary}\n")

    completed_task = finalize_task(
        state_root=state_root,
        repo_record=repo_record,
        task=task,
        session_record=session_record,
        exit_code=exit_code,
        summary=summary,
        notification_title=f"Delegated task {task['task_id']}",
    )
    orchestrator.start_eligible_tasks(state_root, repo_record, tmux_bin=shutil.which("tmux") or "tmux")
    return {"task": completed_task, "cwd": str(cwd), "command": command}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--state-root", default=str(orchestrator.DEFAULT_STATE_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    state_root = orchestrator.resolve_state_root(args.state_root)

    try:
        result = run_task(Path(args.task_file).expanduser().resolve(), state_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
