import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "knowledge_space_skill_forge.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "knowledge_space_skill_forge", MODULE_PATH
)
knowledge_space_skill_forge = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(knowledge_space_skill_forge)


class KnowledgeSpaceSkillForgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_spec = {
            "slug": "dependency-incident-triage",
            "name": "dependency-incident-triage",
            "description": "Capture the reusable workflow for debugging and stabilizing a failing dependency upgrade.",
            "purpose": "Use this skill when a dependency update causes test failures, build errors, or rollout risk.",
            "workflow": [
                "Restate the dependency change and the observed failure.",
                "Find the smallest reproducible failure.",
                "Define validation and rollback checks.",
            ],
            "output_format": [
                {
                    "heading": "Failure summary",
                    "bullets": ["What changed", "What broke"],
                },
                {
                    "heading": "Recovery plan",
                    "bullets": ["Immediate mitigation", "Validation steps"],
                },
            ],
            "quality_bar": ["Prefer reversible fixes first."],
        }

    def test_render_skill_contains_expected_sections(self) -> None:
        rendered = knowledge_space_skill_forge.render_skill(self.sample_spec)

        self.assertIn("name: dependency-incident-triage", rendered)
        self.assertIn("# Purpose", rendered)
        self.assertIn("# Workflow", rendered)
        self.assertIn("# Output format", rendered)
        self.assertIn("## Failure summary", rendered)
        self.assertIn("# Quality bar", rendered)

    def test_normalize_skills_dir_accepts_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            skills_dir = repo_root / "skills"
            skills_dir.mkdir()

            resolved = knowledge_space_skill_forge.normalize_skills_dir(repo_root)

            self.assertEqual(resolved, skills_dir.resolve())

    def test_resolve_skills_dir_uses_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            skills_dir = repo_root / "skills"
            skills_dir.mkdir()

            with mock.patch.dict(
                os.environ,
                {knowledge_space_skill_forge.SKILLS_DIRS_ENV: str(repo_root)},
                clear=False,
            ):
                resolved = knowledge_space_skill_forge.resolve_skills_dir(None)

            self.assertEqual(resolved, skills_dir.resolve())

    def test_write_skill_creates_skill_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            skill_path = knowledge_space_skill_forge.write_skill(skills_dir, self.sample_spec)

            self.assertTrue(skill_path.is_file())
            self.assertIn("# Workflow", skill_path.read_text())

    def test_load_spec_requires_required_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            spec_path = Path(temp_dir) / "spec.json"
            spec_path.write_text(json.dumps({"slug": "missing-fields"}))

            with self.assertRaises(ValueError):
                knowledge_space_skill_forge.load_spec(spec_path)


if __name__ == "__main__":
    unittest.main()
