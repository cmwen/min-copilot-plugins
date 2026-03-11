#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

SKILLS_DIRS_ENV = "COPILOT_CUSTOM_SKILLS_DIRS"
SKILL_REPO_ENV = "COPILOT_CUSTOM_SKILL_REPO"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render or sync a Copilot skill into a user-managed skills repository."
    )
    parser.add_argument(
        "--spec-file",
        required=True,
        help="Path to a JSON file describing the skill to create or update.",
    )
    parser.add_argument(
        "--skills-dir",
        help="Optional override for the skills directory or its repository root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated SKILL.md content instead of writing files.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Stage and commit the generated skill after writing it.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the committed change after writing it. Requires --commit.",
    )
    parser.add_argument(
        "--commit-message",
        help="Commit message to use with --commit. Defaults to the skill name.",
    )
    return parser.parse_args()


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text())
    for required_key in ("slug", "name", "description", "purpose", "workflow", "output_format"):
        if required_key not in spec:
            raise ValueError(f"Missing required spec key: {required_key}")
    if not isinstance(spec["workflow"], list) or not spec["workflow"]:
        raise ValueError("'workflow' must be a non-empty list")
    if not isinstance(spec["output_format"], list) or not spec["output_format"]:
        raise ValueError("'output_format' must be a non-empty list")
    return spec


def candidate_paths(explicit: str | None) -> Iterable[Path]:
    if explicit:
        yield Path(explicit).expanduser()

    env_dirs = os.getenv(SKILLS_DIRS_ENV)
    if env_dirs:
        for value in env_dirs.split(os.pathsep):
            if value:
                yield Path(value).expanduser()

    env_repo = os.getenv(SKILL_REPO_ENV)
    if env_repo:
        yield Path(env_repo).expanduser()


def normalize_skills_dir(candidate: Path) -> Path | None:
    if candidate.is_dir() and candidate.name == "skills":
        return candidate.resolve()
    nested = candidate / "skills"
    if nested.is_dir():
        return nested.resolve()
    return None


def resolve_skills_dir(explicit: str | None) -> Path:
    attempted: list[str] = []
    for candidate in candidate_paths(explicit):
        attempted.append(str(candidate))
        normalized = normalize_skills_dir(candidate)
        if normalized is not None:
            return normalized

    joined_attempts = ", ".join(attempted) if attempted else "<none>"
    raise SystemExit(
        "Could not resolve a skills directory. "
        f"Checked: {joined_attempts}. "
        f"Set {SKILLS_DIRS_ENV}, set {SKILL_REPO_ENV}, or pass --skills-dir."
    )


def render_bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def render_output_format(sections: list[dict]) -> list[str]:
    lines: list[str] = []
    for section in sections:
        heading = section.get("heading")
        bullets = section.get("bullets")
        if not heading or not isinstance(bullets, list) or not bullets:
            raise ValueError("Each output_format item must have 'heading' and non-empty 'bullets'")
        lines.append(f"## {heading}")
        lines.extend(render_bullets(bullets))
        lines.append("")
    return lines


def render_skill(spec: dict) -> str:
    lines = [
        "---",
        f"name: {spec['name']}",
        f"description: {spec['description']}",
        "---",
        "",
        "# Purpose",
        "",
        spec["purpose"],
        "",
        "# Workflow",
        "",
    ]

    for index, step in enumerate(spec["workflow"], start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "# Output format",
            "",
        ]
    )
    lines.extend(render_output_format(spec["output_format"]))

    quality_bar = spec.get("quality_bar", [])
    if quality_bar:
        lines.extend(
            [
                "# Quality bar",
                "",
                *render_bullets(quality_bar),
                "",
            ]
        )

    examples = spec.get("examples", [])
    if examples:
        lines.extend(
            [
                "# Examples",
                "",
                *render_bullets(examples),
                "",
            ]
        )

    notes = spec.get("notes", [])
    if notes:
        lines.extend(
            [
                "# Notes",
                "",
                *render_bullets(notes),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_skill(skills_dir: Path, spec: dict) -> Path:
    skill_dir = skills_dir / spec["slug"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(render_skill(spec))
    return skill_path


def find_git_root(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def git_commit(skill_dir: Path, skill_name: str, commit_message: str | None, push: bool) -> None:
    repo_root = find_git_root(skill_dir)
    if repo_root is None:
        raise SystemExit("Cannot commit because the target skills directory is not inside a git repository.")

    relative_path = skill_dir.resolve().relative_to(repo_root)
    subprocess.run(["git", "-C", str(repo_root), "add", str(relative_path)], check=True)

    message = commit_message or f"Add or update skill: {skill_name}"
    subprocess.run(["git", "-C", str(repo_root), "commit", "-m", message], check=True)

    if push:
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True)


def main() -> None:
    args = parse_args()
    if args.push and not args.commit:
        raise SystemExit("--push requires --commit so the generated change is committed first.")

    spec = load_spec(Path(args.spec_file).expanduser())
    skills_dir = resolve_skills_dir(args.skills_dir)
    skill_path = skills_dir / spec["slug"] / "SKILL.md"
    rendered = render_skill(spec)

    print(f"Target skills directory: {skills_dir}")
    print(f"Target skill file: {skill_path}")

    if args.dry_run:
        print("\n--- BEGIN SKILL ---\n")
        print(rendered, end="")
        print("--- END SKILL ---")
        return

    written_path = write_skill(skills_dir, spec)
    print(f"Wrote {written_path}")

    if args.commit:
        git_commit(written_path.parent, spec["name"], args.commit_message, args.push)
        if args.push:
            print("Committed and pushed the generated skill.")
        else:
            print("Committed the generated skill.")


if __name__ == "__main__":
    main()
