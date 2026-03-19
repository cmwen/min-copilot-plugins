"""Tests for tmux_cli_orchestrator.py."""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "tmux_cli_orchestrator.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "tmux_cli_orchestrator", MODULE_PATH
)
orchestrator = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(orchestrator)


class OrchestratorFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_root = Path(self.tmp.name) / "state"
        self.repo_root = Path(self.tmp.name) / "repo"
        self.repo_root.mkdir()
        (self.repo_root / ".git").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()


class TestRegisterRepo(OrchestratorFixture):
    @mock.patch.object(orchestrator, "detect_git_root")
    def test_register_repo_persists_memory(self, detect_git_root):
        detect_git_root.return_value = self.repo_root
        result = orchestrator.register_repo(
            self.state_root,
            str(self.repo_root),
            purpose="Build a delegated worker plugin.",
            alias="delegated-demo",
            default_cli="opencode",
        )

        self.assertEqual(result["repo"]["purpose"], "Build a delegated worker plugin.")
        self.assertEqual(result["repo"]["default_cli"], "opencode")
        self.assertEqual(result["repo"]["alias"], "delegated-demo")
        self.assertTrue(
            orchestrator.repo_metadata_path(self.state_root, result["repo"]["repo_id"]).exists()
        )


class TestCreateTaskRecord(OrchestratorFixture):
    @mock.patch.object(orchestrator, "detect_git_root")
    def test_enqueue_task_creates_prompt_copy_and_defaults_title(self, detect_git_root):
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

        task = orchestrator.create_task_record(
            repo_dir,
            repo_record,
            cli="copilot",
            execution_mode="queue",
            prompt_text="Investigate flaky tests and fix them.",
            prompt_source_path=None,
            title=None,
            preferred_session_id=None,
            cleanup_prompt_file=True,
            agent_name=None,
            model_name=None,
        )

        self.assertEqual(task["status"], "queued")
        self.assertIsNotNone(task["prompt_file"])
        self.assertTrue(Path(task["prompt_file"]).exists())
        self.assertIn("Investigate flaky tests", task["title"])


class TestScheduling(OrchestratorFixture):
    @mock.patch.object(orchestrator, "send_task_to_panes")
    @mock.patch.object(orchestrator, "detect_git_root")
    def test_start_eligible_tasks_respects_single_queue_task(self, detect_git_root, send_task_to_panes):
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

        session_one = {
            "active_task_id": None,
            "cli": "copilot",
            "created_at": orchestrator.utc_now(),
            "label": "one",
            "last_used_at": orchestrator.utc_now(),
            "repo_id": repo_record["repo_id"],
            "runner_pane_id": "%1",
            "session_id": "one",
            "status": "idle",
            "status_pane_id": "%2",
            "tmux_session_name": repo_record["tmux_session_name"],
            "window_name": "one",
        }
        session_two = dict(session_one)
        session_two.update({"session_id": "two", "window_name": "two", "runner_pane_id": "%3", "status_pane_id": "%4"})
        orchestrator.update_session_record(repo_dir, session_one)
        orchestrator.update_session_record(repo_dir, session_two)

        task_one = orchestrator.create_task_record(
            repo_dir,
            repo_record,
            cli="copilot",
            execution_mode="queue",
            prompt_text="Task one",
            prompt_source_path=None,
            title="Task one",
            preferred_session_id=None,
            cleanup_prompt_file=True,
            agent_name=None,
            model_name=None,
        )
        task_two = orchestrator.create_task_record(
            repo_dir,
            repo_record,
            cli="copilot",
            execution_mode="queue",
            prompt_text="Task two",
            prompt_source_path=None,
            title="Task two",
            preferred_session_id=None,
            cleanup_prompt_file=True,
            agent_name=None,
            model_name=None,
        )
        task_three = orchestrator.create_task_record(
            repo_dir,
            repo_record,
            cli="opencode",
            execution_mode="worktree",
            prompt_text="Task three",
            prompt_source_path=None,
            title="Task three",
            preferred_session_id=None,
            cleanup_prompt_file=True,
            agent_name=None,
            model_name=None,
        )

        with mock.patch.object(orchestrator, "shutil") as mock_shutil:
            mock_shutil.which.return_value = "/opt/homebrew/bin/tmux"
            result = orchestrator.start_eligible_tasks(self.state_root, repo_record, tmux_bin="tmux")

        self.assertEqual(result["started_task_ids"], [task_one["task_id"], task_three["task_id"]])
        queued = orchestrator.load_task(repo_dir, task_two["task_id"])
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(send_task_to_panes.call_count, 2)


class TestCommandLine(OrchestratorFixture):
    @mock.patch.object(orchestrator, "detect_git_root")
    def test_main_repo_register_and_show(self, detect_git_root):
        detect_git_root.return_value = self.repo_root
        with redirect_stdout(io.StringIO()):
            exit_code = orchestrator.main(
                [
                    "--state-root",
                    str(self.state_root),
                    "repo-register",
                    "--repo-root",
                    str(self.repo_root),
                    "--purpose",
                    "Delegated orchestration demo",
                ]
            )
        self.assertEqual(exit_code, 0)

        repo_id = orchestrator.build_repo_id(self.repo_root)
        with redirect_stdout(io.StringIO()):
            show_code = orchestrator.main(
                [
                    "--state-root",
                    str(self.state_root),
                    "repo-show",
                    "--repo-id",
                    repo_id,
                ]
            )
        self.assertEqual(show_code, 0)
