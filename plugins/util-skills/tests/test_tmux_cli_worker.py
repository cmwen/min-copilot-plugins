"""Tests for tmux_cli_worker.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ORCH_PATH = SCRIPTS_DIR / "tmux_cli_orchestrator.py"
ORCH_SPEC = importlib.util.spec_from_file_location("tmux_cli_orchestrator", ORCH_PATH)
orchestrator = importlib.util.module_from_spec(ORCH_SPEC)
assert ORCH_SPEC.loader is not None
ORCH_SPEC.loader.exec_module(orchestrator)
sys.modules["tmux_cli_orchestrator"] = orchestrator

WORKER_PATH = SCRIPTS_DIR / "tmux_cli_worker.py"
WORKER_SPEC = importlib.util.spec_from_file_location("tmux_cli_worker", WORKER_PATH)
worker = importlib.util.module_from_spec(WORKER_SPEC)
assert WORKER_SPEC.loader is not None
WORKER_SPEC.loader.exec_module(worker)


class WorkerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_root = Path(self.tmp.name) / "state"
        self.repo_root = Path(self.tmp.name) / "repo"
        self.repo_root.mkdir()
        (self.repo_root / ".git").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()


class TestBuildCliCommand(unittest.TestCase):
    def test_builds_copilot_command(self):
        command = worker.build_cli_command(
            cli="copilot",
            prompt_text="Fix the tests.",
            cwd=Path("/tmp/repo"),
            agent_name="delegator",
            model_name="gpt-5.4",
        )
        self.assertIn("copilot", command[0])
        self.assertIn("--agent", command)
        self.assertIn("delegator", command)
        self.assertIn("--model", command)

    def test_builds_opencode_command(self):
        command = worker.build_cli_command(
            cli="opencode",
            prompt_text="Implement feature",
            cwd=Path("/tmp/repo"),
            agent_name=None,
            model_name=None,
        )
        self.assertEqual(command[:2], ["opencode", "run"])
        self.assertEqual(command[-1], "Implement feature")


class TestPrepareWorktree(WorkerFixture):
    @mock.patch.object(orchestrator, "run_command")
    def test_prepare_worktree_runs_git_worktree_add(self, run_command):
        repo_record = {
            "repo_id": "demo-1234",
            "repo_path": str(self.repo_root),
            "git_root": str(self.repo_root),
            "worktree_root": str(self.state_root / "worktrees" / "demo-1234"),
        }
        task = {"task_id": "task123", "execution_mode": "worktree"}
        cwd, worktree_path, branch_name = worker.prepare_worktree(task, repo_record, self.state_root)

        self.assertEqual(cwd, (Path(repo_record["worktree_root"]) / "task123").resolve())
        self.assertEqual(worktree_path, str(cwd))
        self.assertEqual(branch_name, "delegated-task123")
        run_command.assert_called_once()


class TestFinalizeTask(WorkerFixture):
    @mock.patch.object(worker, "send_best_effort_notification", return_value="osascript")
    @mock.patch.object(orchestrator, "display_tmux_message")
    @mock.patch.object(orchestrator, "detect_git_root")
    def test_finalize_task_marks_session_idle(
        self,
        detect_git_root,
        display_tmux_message,
        send_best_effort_notification,
    ):
        detect_git_root.return_value = self.repo_root
        repo_payload = orchestrator.register_repo(
            self.state_root,
            str(self.repo_root),
            purpose="Delegated repo",
            alias=None,
            default_cli="copilot",
        )
        repo_record = repo_payload["repo"]
        repo_dir = orchestrator.repo_state_dir(self.state_root, repo_record["repo_id"])
        orchestrator.ensure_repo_dirs(repo_dir)
        session = {
            "active_task_id": "task123",
            "cli": "copilot",
            "created_at": orchestrator.utc_now(),
            "label": "main",
            "last_used_at": orchestrator.utc_now(),
            "repo_id": repo_record["repo_id"],
            "runner_pane_id": "%1",
            "session_id": "main",
            "status": "busy",
            "status_pane_id": "%2",
            "tmux_session_name": repo_record["tmux_session_name"],
            "window_name": "main",
        }
        orchestrator.update_session_record(repo_dir, session)
        task = orchestrator.create_task_record(
            repo_dir,
            repo_record,
            cli="copilot",
            execution_mode="queue",
            prompt_text="Test prompt",
            prompt_source_path=None,
            title="Test task",
            preferred_session_id="main",
            cleanup_prompt_file=True,
            agent_name=None,
            model_name=None,
        )
        task.update(
            {
                "session_id": "main",
                "status": "running",
                "started_at": orchestrator.utc_now(),
                "log_file": str(repo_dir / "logs" / f"{task['task_id']}.log"),
            }
        )
        orchestrator.update_task_record(repo_dir, task)

        updated = worker.finalize_task(
            state_root=self.state_root,
            repo_record=repo_record,
            task=task,
            session_record=session,
            exit_code=0,
            summary="done",
            notification_title="Delegated task",
        )

        reloaded_session = orchestrator.load_json(
            orchestrator.session_metadata_path(repo_dir, session["session_id"])
        )
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(reloaded_session["status"], "idle")
        display_tmux_message.assert_called_once()
        send_best_effort_notification.assert_called_once()
