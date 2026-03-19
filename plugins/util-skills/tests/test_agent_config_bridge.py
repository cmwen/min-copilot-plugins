"""
Tests for agent_config_bridge.py

Focused on JSONC parsing, repo classification, translation planning, and
filesystem safety behavior.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "agent_config_bridge.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "agent_config_bridge", MODULE_PATH
)
agent_config_bridge = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(agent_config_bridge)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    _write(path, json.dumps(data, indent=2) + "\n")


class RepoFixtureTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class TestJsoncParsing(RepoFixtureTestCase):

    def test_strip_jsonc_comments_preserves_strings(self):
        jsonc_text = """
        {
          // keep this URL untouched
          "url": "https://example.com//path",
          /* translate this config */
          "mcp": {
            "filesystem": {
              "type": "local",
              "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
            }
          }
        }
        """
        stripped = agent_config_bridge.strip_jsonc_comments(jsonc_text)
        data = json.loads(stripped)
        self.assertEqual(data["url"], "https://example.com//path")
        self.assertEqual(data["mcp"]["filesystem"]["type"], "local")


class TestInventoryClassification(RepoFixtureTestCase):

    def test_classifies_copilot_only_repo(self):
        _write_json(
            self.repo_root / "plugins" / "demo" / "plugin.json",
            {"name": "demo", "skills": ["skills/"]},
        )
        _write(
            self.repo_root / "plugins" / "demo" / "skills" / "review" / "SKILL.md",
            "---\nname: review\ndescription: Review code.\n---\n",
        )

        inventory = agent_config_bridge.inventory_repo(self.repo_root)

        self.assertEqual(inventory["classification"], "copilot")

    def test_classifies_opencode_only_repo(self):
        _write(
            self.repo_root / "opencode.jsonc",
            """
            {
              // project-local config
              "mcp": {}
            }
            """,
        )
        _write(
            self.repo_root / ".opencode" / "skills" / "release" / "SKILL.md",
            "---\nname: release\ndescription: Release workflow.\n---\n",
        )

        inventory = agent_config_bridge.inventory_repo(self.repo_root)

        self.assertEqual(inventory["classification"], "opencode")

    def test_classifies_mixed_repo(self):
        _write_json(
            self.repo_root / "plugins" / "demo" / "plugin.json",
            {"name": "demo", "skills": ["skills/"]},
        )
        _write(
            self.repo_root / "opencode.json",
            json.dumps({"mcp": {}}, indent=2) + "\n",
        )

        inventory = agent_config_bridge.inventory_repo(self.repo_root)

        self.assertEqual(inventory["classification"], "mixed")

    def test_classifies_none_when_no_assets_exist(self):
        inventory = agent_config_bridge.inventory_repo(self.repo_root)
        self.assertEqual(inventory["classification"], "none")


class TestPlanGeneration(RepoFixtureTestCase):

    def test_plans_copilot_to_opencode_bridge(self):
        plugin_root = self.repo_root / "plugins" / "demo-plugin"
        _write_json(
            plugin_root / "plugin.json",
            {"name": "demo-plugin", "skills": ["skills/"], "agents": "agents/"},
        )
        _write(
            plugin_root / "skills" / "review" / "SKILL.md",
            "---\nname: review\ndescription: Review code changes.\n---\n",
        )
        _write(
            plugin_root / "agents" / "researcher.agent.md",
            "---\nname: researcher\ndescription: Research technical questions.\n---\n\nBe thorough.\n",
        )
        _write_json(
            plugin_root / ".mcp.json",
            {
                "servers": {
                    "playwright": {
                        "command": "npx",
                        "args": ["-y", "@playwright/mcp@latest"],
                        "env": {"PLAYWRIGHT_BROWSERS_PATH": "0"},
                    }
                }
            },
        )
        _write(
            self.repo_root / ".github" / "copilot-instructions.md",
            "# Repo instructions\n",
        )

        plan = agent_config_bridge.build_plan(
            self.repo_root,
            "opencode",
            source_root="plugins/demo-plugin",
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["source_root"], "plugins/demo-plugin")
        self.assertEqual(plan["target_root"], ".opencode")

        link_actions = [a for a in plan["actions"] if a["action"] == "link"]
        write_file_actions = [a for a in plan["actions"] if a["action"] == "write-file"]
        write_json_actions = [a for a in plan["actions"] if a["action"] == "write-json"]

        self.assertIn(
            ".opencode/skills/review/SKILL.md",
            [action["destination"] for action in link_actions],
        )
        self.assertIn(
            "AGENTS.md",
            [action["destination"] for action in link_actions],
        )
        self.assertIn(
            ".opencode/agents/researcher.md",
            [action["destination"] for action in write_file_actions],
        )
        self.assertTrue(
            any(
                action["destination"] == "opencode.json"
                and action["data"]["mcp"]["playwright"]["environment"][
                    "PLAYWRIGHT_BROWSERS_PATH"
                ]
                == "0"
                for action in write_json_actions
            )
        )
        self.assertTrue(
            any(
                "Imported from GitHub Copilot CLI agent" in action["content"]
                for action in write_file_actions
            )
        )

    def test_plans_opencode_to_copilot_bridge(self):
        _write(
            self.repo_root / ".opencode" / "skills" / "release" / "SKILL.md",
            "---\nname: release\ndescription: Prepare releases.\n---\n",
        )
        _write(
            self.repo_root / ".opencode" / "agents" / "researcher.md",
            "---\ndescription: Research and summarize findings.\n---\n\nStay precise.\n",
        )
        _write(
            self.repo_root / ".opencode" / "commands" / "ship.md",
            "---\ndescription: Ship a release.\n---\n\nPublish version $1.\n",
        )
        _write(
            self.repo_root / "opencode.jsonc",
            """
            {
              "mcp": {
                "filesystem": {
                  "type": "local",
                  "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem"],
                  "environment": {
                    "FS_ROOT": "."
                  }
                },
                "github": {
                  "type": "remote",
                  "url": "https://example.com/mcp"
                }
              }
            }
            """,
        )

        plan = agent_config_bridge.build_plan(
            self.repo_root,
            "copilot",
            source_root=".opencode",
            target_root="plugins/demo-bridge",
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["source_root"], ".opencode")
        self.assertEqual(plan["target_root"], "plugins/demo-bridge")

        actions_by_type = {}
        for action in plan["actions"]:
            actions_by_type.setdefault(action["action"], []).append(action)

        self.assertIn(
            "plugins/demo-bridge/skills/release/SKILL.md",
            [action["destination"] for action in actions_by_type["link"]],
        )
        self.assertIn(
            "plugins/demo-bridge/agents/researcher.agent.md",
            [action["destination"] for action in actions_by_type["write-file"]],
        )
        self.assertIn(
            "plugins/demo-bridge/skills/ship/source-command.md",
            [action["destination"] for action in actions_by_type["link"]],
        )
        self.assertIn(
            "plugins/demo-bridge/skills/ship/SKILL.md",
            [action["destination"] for action in actions_by_type["write-file"]],
        )
        self.assertTrue(
            any(
                action["destination"] == "plugins/demo-bridge/.mcp.json"
                and action["data"]["servers"]["filesystem"]["env"]["FS_ROOT"] == "."
                for action in actions_by_type["write-json"]
            )
        )
        self.assertTrue(
            any(
                action["destination"] == "plugins/demo-bridge/plugin.json"
                and action["data"]["agents"] == "agents/"
                and action["data"]["mcpServers"] == ".mcp.json"
                for action in actions_by_type["write-json"]
            )
        )
        self.assertTrue(
            any(
                action["action"] == "skip"
                and "Copilot .mcp.json" in action["reason"]
                for action in plan["actions"]
            )
        )


class TestApplyPlan(RepoFixtureTestCase):

    def test_apply_plan_creates_relative_symlink_and_is_idempotent(self):
        _write(self.repo_root / "source.txt", "hello\n")
        plan = {
            "repo_root": str(self.repo_root),
            "status": "ready",
            "actions": [
                {
                    "action": "link",
                    "source": "source.txt",
                    "destination": "nested/link.txt",
                    "reason": "Direct reuse.",
                }
            ],
        }

        first = agent_config_bridge.apply_plan(plan)
        second = agent_config_bridge.apply_plan(plan)
        link_path = self.repo_root / "nested" / "link.txt"

        self.assertEqual(first["summary"]["linked"], 1)
        self.assertEqual(second["summary"]["kept"], 1)
        self.assertTrue(link_path.is_symlink())
        self.assertFalse(os.readlink(link_path).startswith("/"))

    def test_apply_plan_refuses_to_overwrite_regular_file(self):
        _write(self.repo_root / "source.txt", "hello\n")
        _write(self.repo_root / "nested" / "link.txt", "existing\n")
        plan = {
            "repo_root": str(self.repo_root),
            "status": "ready",
            "actions": [
                {
                    "action": "link",
                    "source": "source.txt",
                    "destination": "nested/link.txt",
                    "reason": "Direct reuse.",
                }
            ],
        }

        with self.assertRaises(FileExistsError):
            agent_config_bridge.apply_plan(plan)

    def test_apply_plan_refuses_repo_escape_destination(self):
        _write(self.repo_root / "source.txt", "hello\n")
        plan = {
            "repo_root": str(self.repo_root),
            "status": "ready",
            "actions": [
                {
                    "action": "link",
                    "source": "source.txt",
                    "destination": "../escape.txt",
                    "reason": "Unsafe path.",
                }
            ],
        }

        with self.assertRaises(ValueError):
            agent_config_bridge.apply_plan(plan)


if __name__ == "__main__":
    unittest.main()
