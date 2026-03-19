"""Utilities for scanning and bridging Copilot CLI and OpenCode repository config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments from JSONC text while preserving strings."""
    result: list[str] = []
    in_string = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    index = 0
    length = len(text)

    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            index += 1
            continue

        if in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue

        if char == "/" and nxt == "/":
            in_line_comment = True
            index += 2
            continue

        if char == "/" and nxt == "*":
            in_block_comment = True
            index += 2
            continue

        result.append(char)
        index += 1

    if in_block_comment:
        raise ValueError("Unterminated block comment in JSONC input.")

    return "".join(result)


def load_json_or_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonc":
        text = strip_jsonc_comments(text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _safe_resolve_within_repo(repo_root: Path, raw_path: str | Path, *, must_exist: bool) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes repository root: {raw_path}") from exc
    return resolved


def _split_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown
    closing = markdown.find("\n---\n", 4)
    if closing == -1:
        return {}, markdown
    raw_meta = markdown[4:closing]
    body = markdown[closing + 5 :]
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.lstrip("\n")


def _best_description(path: Path, markdown: str, metadata: dict[str, str]) -> str:
    description = metadata.get("description")
    if description:
        return description
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped[:140]
    stem = path.stem
    if stem.endswith(".agent"):
        stem = stem[: -len(".agent")]
    return stem.replace("-", " ").strip().title()


def _agent_stem(path: Path) -> str:
    name = path.name
    if name.endswith(".agent.md"):
        return name[: -len(".agent.md")]
    if name.endswith(".md"):
        return name[: -len(".md")]
    return path.stem


def _choose_copilot_source(repo_root: Path, inventory: dict[str, Any], source_root: str | None) -> tuple[Path | None, list[str]]:
    notes: list[str] = []
    plugin_roots = [repo_root / item["root"] for item in inventory["copilot"]["plugin_roots"]]
    if source_root:
        try:
            chosen = _safe_resolve_within_repo(repo_root, source_root, must_exist=True)
        except ValueError as exc:
            return None, [str(exc)]
        if not (chosen / "plugin.json").is_file():
            return None, [f"Source root {chosen} does not contain plugin.json."]
        return chosen, notes
    if not plugin_roots:
        return None, ["No Copilot plugin root was found."]
    if len(plugin_roots) > 1:
        notes.append("Multiple Copilot plugin roots were found; pass --source-root to choose one explicitly.")
        return None, notes
    return plugin_roots[0], notes


def _choose_opencode_sources(repo_root: Path, inventory: dict[str, Any], source_root: str | None) -> tuple[Path | None, Path | None, list[str], bool]:
    notes: list[str] = []
    repo_root = repo_root.resolve()
    actual_skill_roots = [repo_root / entry["root"] for entry in inventory["opencode"]["skill_roots"]]
    source_supports_wrappers = True

    if source_root:
        try:
            chosen = _safe_resolve_within_repo(repo_root, source_root, must_exist=True)
        except ValueError as exc:
            return None, None, [str(exc)], False
        if chosen == repo_root:
            if len(actual_skill_roots) > 1:
                notes.append("The repository contains multiple OpenCode skill roots; choose one specific source root such as .opencode, .claude, or .agents.")
                return None, None, notes, False
            skill_root = actual_skill_roots[0] if actual_skill_roots else None
            return chosen, skill_root, notes, True
        if chosen.name in {".opencode", ".claude", ".agents"}:
            skill_root = chosen if (chosen / "skills").exists() else None
            source_supports_wrappers = chosen.name == ".opencode"
            return chosen, skill_root, notes, source_supports_wrappers
        notes.append("Unsupported OpenCode source root. Use the repository root or one of .opencode, .claude, or .agents.")
        return None, None, notes, False

    if len(actual_skill_roots) > 1:
        notes.append("Multiple OpenCode skill roots were found; pass --source-root to choose .opencode, .claude, or .agents explicitly.")
        return None, None, notes, False

    skill_root = actual_skill_roots[0] if actual_skill_roots else None
    return repo_root, skill_root, notes, True


def _copilot_agent_to_opencode_wrapper(source_rel: str, source_path: Path) -> str:
    markdown = source_path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(markdown)
    name = metadata.get("name") or _agent_stem(source_path)
    description = _best_description(source_path, body, metadata)
    cleaned_body = body.strip()
    return (
        f"---\ndescription: {description}\n---\n\n"
        f"Imported from GitHub Copilot CLI agent `{source_rel}`.\n\n"
        f"{cleaned_body or '(No prompt body was present in the source agent.)'}\n"
    )


def _opencode_agent_to_copilot_wrapper(source_rel: str, source_path: Path) -> str:
    markdown = source_path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(markdown)
    name = metadata.get("name") or _agent_stem(source_path)
    description = _best_description(source_path, body, metadata)
    cleaned_body = body.strip()
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        f"Imported from OpenCode agent `{source_rel}`.\n\n"
        f"{cleaned_body or '(No prompt body was present in the source agent.)'}\n"
    )


def _command_to_skill_wrapper(source_rel: str, source_path: Path) -> str:
    markdown = source_path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(markdown)
    name = source_path.stem
    description = _best_description(source_path, body, metadata)
    return (
        f"---\nname: {name}\ndescription: Imported OpenCode command wrapper for {description}.\n---\n\n"
        "# Purpose\n\n"
        f"Use this skill when the user wants the workflow captured in the imported OpenCode command `{name}`.\n"
        "This wrapper preserves the original command template in `source-command.md` and asks Copilot to follow it explicitly rather than guessing.\n\n"
        "# Workflow\n\n"
        "1. Read `source-command.md` before acting.\n"
        "2. Preserve the original command template semantics, placeholders, arguments, and safety constraints.\n"
        "3. If the command relies on missing arguments or context, ask the user to provide them explicitly instead of inventing values.\n"
        "4. Mention that this skill was imported from OpenCode and summarize any ecosystem-specific assumptions that may need adaptation for Copilot CLI.\n\n"
        "# Output expectations\n\n"
        "Return the final result the command asks for, plus a short note describing any assumptions or adaptations needed for Copilot CLI.\n\n"
        "# Imported source\n\n"
        f"Original file: `{source_rel}`\n"
    )


def _translate_copilot_mcp_to_opencode(source_path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    data = load_json_or_jsonc(source_path)
    servers = data.get("servers", {})
    translated: dict[str, Any] = {}
    skips: list[dict[str, str]] = []
    if not isinstance(servers, dict):
        return translated, [{"server": "*", "reason": "Copilot MCP file does not contain a top-level servers object."}]
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            skips.append({"server": name, "reason": "Server entry is not an object."})
            continue
        command = entry.get("command")
        args = entry.get("args", [])
        if not isinstance(command, str) or not command:
            skips.append({"server": name, "reason": "Only local command-based Copilot MCP servers can be translated."})
            continue
        if args is None:
            args = []
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            skips.append({"server": name, "reason": "Server args must be a list of strings."})
            continue
        translated_entry: dict[str, Any] = {
            "type": "local",
            "command": [command, *args],
            "enabled": True,
        }
        env = entry.get("env")
        if isinstance(env, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            translated_entry["environment"] = env
        translated[name] = translated_entry
    return translated, skips


def _translate_opencode_mcp_to_copilot(config_data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    mcp = config_data.get("mcp", {})
    translated: dict[str, Any] = {}
    skips: list[dict[str, str]] = []
    if not isinstance(mcp, dict):
        return translated, [{"server": "*", "reason": "OpenCode config does not contain an mcp object."}]
    for name, entry in mcp.items():
        if not isinstance(entry, dict):
            skips.append({"server": name, "reason": "Server entry is not an object."})
            continue
        if entry.get("type") != "local":
            skips.append({"server": name, "reason": "Only local OpenCode MCP servers can be translated into Copilot .mcp.json."})
            continue
        command = entry.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            skips.append({"server": name, "reason": "Local OpenCode MCP command must be a non-empty string array."})
            continue
        translated_entry: dict[str, Any] = {
            "command": command[0],
            "args": command[1:],
        }
        environment = entry.get("environment")
        if isinstance(environment, dict) and all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in environment.items()
        ):
            translated_entry["env"] = environment
        translated[name] = translated_entry
    return translated, skips


def inventory_repo(repo_root: str | Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    plugin_json_paths = sorted(path for path in repo_root.rglob("plugin.json") if path.is_file())
    copilot_plugin_roots = []
    copilot_agents: list[str] = []
    copilot_skills: list[str] = []
    copilot_mcp_files: list[str] = []

    for plugin_json in plugin_json_paths:
        root = plugin_json.parent
        mcp_json = root / ".mcp.json"
        agents = sorted(path for path in root.glob("agents/**/*.agent.md") if path.is_file())
        skills = sorted(path for path in root.glob("skills/*/SKILL.md") if path.is_file())
        root_entry = {
            "root": _relative_to_repo(repo_root, root),
            "plugin_json": _relative_to_repo(repo_root, plugin_json),
            "mcp_json": _relative_to_repo(repo_root, mcp_json) if mcp_json.is_file() else None,
            "agents": [_relative_to_repo(repo_root, path) for path in agents],
            "skills": [_relative_to_repo(repo_root, path) for path in skills],
        }
        copilot_plugin_roots.append(root_entry)
        copilot_agents.extend(root_entry["agents"])
        copilot_skills.extend(root_entry["skills"])
        if root_entry["mcp_json"]:
            copilot_mcp_files.append(root_entry["mcp_json"])

    github_copilot_instructions = repo_root / ".github" / "copilot-instructions.md"
    github_instruction_files = sorted(
        path for path in (repo_root / ".github" / "instructions").glob("**/*.md") if path.is_file()
    ) if (repo_root / ".github" / "instructions").exists() else []

    opencode_configs = []
    for name in ("opencode.json", "opencode.jsonc"):
        path = repo_root / name
        if path.is_file():
            opencode_configs.append({
                "path": _relative_to_repo(repo_root, path),
                "format": path.suffix.lstrip("."),
                "data": load_json_or_jsonc(path),
            })

    opencode_skill_roots = []
    opencode_skill_files: list[str] = []
    for root_name in (".opencode", ".claude", ".agents"):
        skill_root = repo_root / root_name / "skills"
        files = sorted(path for path in skill_root.glob("*/SKILL.md") if path.is_file()) if skill_root.exists() else []
        if files:
            opencode_skill_roots.append({
                "root": _relative_to_repo(repo_root, repo_root / root_name),
                "skills": [_relative_to_repo(repo_root, path) for path in files],
            })
            opencode_skill_files.extend(_relative_to_repo(repo_root, path) for path in files)

    opencode_agent_files = sorted(
        _relative_to_repo(repo_root, path)
        for path in (repo_root / ".opencode" / "agents").glob("*.md")
        if path.is_file()
    ) if (repo_root / ".opencode" / "agents").exists() else []

    opencode_command_files = sorted(
        _relative_to_repo(repo_root, path)
        for path in (repo_root / ".opencode" / "commands").glob("*.md")
        if path.is_file()
    ) if (repo_root / ".opencode" / "commands").exists() else []

    rule_files = []
    for name in ("AGENTS.md", "CLAUDE.md"):
        path = repo_root / name
        if path.is_file():
            rule_files.append(_relative_to_repo(repo_root, path))

    has_copilot = any([
        copilot_plugin_roots,
        copilot_agents,
        copilot_skills,
        copilot_mcp_files,
        github_copilot_instructions.is_file(),
        github_instruction_files,
    ])
    has_opencode = any([
        opencode_configs,
        opencode_skill_files,
        opencode_agent_files,
        opencode_command_files,
        rule_files,
    ])
    if has_copilot and has_opencode:
        classification = "mixed"
    elif has_copilot:
        classification = "copilot"
    elif has_opencode:
        classification = "opencode"
    else:
        classification = "none"

    return {
        "repo_root": str(repo_root),
        "classification": classification,
        "copilot": {
            "plugin_roots": copilot_plugin_roots,
            "mcp_files": sorted(copilot_mcp_files),
            "agents": sorted(copilot_agents),
            "skills": sorted(copilot_skills),
            "copilot_instructions": _relative_to_repo(repo_root, github_copilot_instructions) if github_copilot_instructions.is_file() else None,
            "instruction_files": [_relative_to_repo(repo_root, path) for path in github_instruction_files],
        },
        "opencode": {
            "config_files": opencode_configs,
            "skill_roots": opencode_skill_roots,
            "skills": sorted(opencode_skill_files),
            "agents": opencode_agent_files,
            "commands": opencode_command_files,
            "rules": rule_files,
        },
    }


def _destination_conflict(seen: dict[str, str], destination: str, reason: str) -> str | None:
    if destination in seen:
        return f"Destination collision with another planned action ({seen[destination]})."
    seen[destination] = reason
    return None


def build_plan(repo_root: str | Path, target: str, *, source_root: str | None = None, target_root: str | None = None) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    inventory = inventory_repo(repo_root)
    plan: dict[str, Any] = {
        "repo_root": str(repo_root),
        "classification": inventory["classification"],
        "target": target,
        "status": "ready",
        "source_root": None,
        "target_root": None,
        "actions": [],
        "notes": [],
    }
    seen_destinations: dict[str, str] = {}

    if target not in {"copilot", "opencode"}:
        plan["status"] = "error"
        plan["notes"].append("Target must be either 'copilot' or 'opencode'.")
        return plan

    if target == "opencode":
        chosen_source, source_notes = _choose_copilot_source(repo_root, inventory, source_root)
        plan["notes"].extend(source_notes)
        if chosen_source is None:
            plan["status"] = "ambiguous" if source_notes else "error"
            return plan
        try:
            chosen_target = _safe_resolve_within_repo(repo_root, target_root or ".opencode", must_exist=False)
        except ValueError as exc:
            plan["status"] = "error"
            plan["notes"].append(str(exc))
            return plan
        plan["source_root"] = _relative_to_repo(repo_root, chosen_source)
        plan["target_root"] = _relative_to_repo(repo_root, chosen_target)

        for skill_path in sorted(path for path in (chosen_source / "skills").glob("*/SKILL.md") if path.is_file()):
            skill_name = skill_path.parent.name
            destination = chosen_target / "skills" / skill_name / "SKILL.md"
            destination_rel = _relative_to_repo(repo_root, destination)
            collision = _destination_conflict(seen_destinations, destination_rel, f"skill {skill_name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
                continue
            plan["actions"].append({
                "action": "link",
                "source": _relative_to_repo(repo_root, skill_path),
                "destination": destination_rel,
                "reason": "Copilot skills use SKILL.md and can be symlinked directly into OpenCode skill directories.",
            })

        for agent_path in sorted(path for path in (chosen_source / "agents").glob("**/*.agent.md") if path.is_file()):
            name = _agent_stem(agent_path)
            destination = chosen_target / "agents" / f"{name}.md"
            destination_rel = _relative_to_repo(repo_root, destination)
            collision = _destination_conflict(seen_destinations, destination_rel, f"agent {name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
                continue
            plan["actions"].append({
                "action": "write-file",
                "destination": destination_rel,
                "content": _copilot_agent_to_opencode_wrapper(_relative_to_repo(repo_root, agent_path), agent_path),
                "reason": "Copilot agent markdown needs an OpenCode wrapper because the agent schemas differ.",
            })

        mcp_file = chosen_source / ".mcp.json"
        existing_configs = inventory["opencode"]["config_files"]
        if mcp_file.is_file():
            translated_servers, skipped_servers = _translate_copilot_mcp_to_opencode(mcp_file)
            for skip in skipped_servers:
                plan["actions"].append({
                    "action": "skip",
                    "source": _relative_to_repo(repo_root, mcp_file),
                    "reason": f"MCP server {skip['server']}: {skip['reason']}",
                })
            if translated_servers:
                config_dest_rel = "opencode.json"
                if existing_configs:
                    plan["actions"].append({
                        "action": "skip",
                        "destination": config_dest_rel,
                        "reason": "An OpenCode config file already exists; refusing to guess how to merge translated MCP servers.",
                    })
                else:
                    collision = _destination_conflict(seen_destinations, config_dest_rel, "opencode mcp")
                    if collision:
                        plan["actions"].append({"action": "skip", "destination": config_dest_rel, "reason": collision})
                    else:
                        plan["actions"].append({
                            "action": "write-json",
                            "destination": config_dest_rel,
                            "data": {"mcp": translated_servers},
                            "reason": "Translate Copilot local MCP servers into OpenCode opencode.json format.",
                        })

        copilot_instructions = inventory["copilot"]["copilot_instructions"]
        if copilot_instructions and "AGENTS.md" not in inventory["opencode"]["rules"]:
            destination_rel = "AGENTS.md"
            collision = _destination_conflict(seen_destinations, destination_rel, "AGENTS instructions")
            if collision:
                plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
            else:
                plan["actions"].append({
                    "action": "link",
                    "source": copilot_instructions,
                    "destination": destination_rel,
                    "reason": "AGENTS.md can safely point at existing Copilot instructions when no AGENTS.md file exists yet.",
                })
        return plan

    chosen_source, chosen_skill_root, source_notes, include_root_wrappers = _choose_opencode_sources(repo_root, inventory, source_root)
    plan["notes"].extend(source_notes)
    if chosen_source is None:
        plan["status"] = "ambiguous" if source_notes else "error"
        return plan

    default_target = repo_root / "plugins" / f"{repo_root.name}-bridge"
    try:
        chosen_target = _safe_resolve_within_repo(repo_root, target_root or default_target, must_exist=False)
    except ValueError as exc:
        plan["status"] = "error"
        plan["notes"].append(str(exc))
        return plan
    plan["source_root"] = _relative_to_repo(repo_root, chosen_source)
    plan["target_root"] = _relative_to_repo(repo_root, chosen_target)

    if chosen_skill_root:
        for skill_path in sorted(path for path in (chosen_skill_root / "skills").glob("*/SKILL.md") if path.is_file()):
            skill_name = skill_path.parent.name
            destination = chosen_target / "skills" / skill_name / "SKILL.md"
            destination_rel = _relative_to_repo(repo_root, destination)
            collision = _destination_conflict(seen_destinations, destination_rel, f"skill {skill_name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
                continue
            plan["actions"].append({
                "action": "link",
                "source": _relative_to_repo(repo_root, skill_path),
                "destination": destination_rel,
                "reason": "OpenCode skills are compatible with Copilot skill directories and can be symlinked directly.",
            })

    generated_agents = False
    generated_mcp = False

    if include_root_wrappers:
        opencode_agents_root = repo_root / ".opencode" / "agents"
        for agent_path in sorted(path for path in opencode_agents_root.glob("*.md") if path.is_file()):
            name = agent_path.stem
            destination = chosen_target / "agents" / f"{name}.agent.md"
            destination_rel = _relative_to_repo(repo_root, destination)
            collision = _destination_conflict(seen_destinations, destination_rel, f"agent {name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
                continue
            generated_agents = True
            plan["actions"].append({
                "action": "write-file",
                "destination": destination_rel,
                "content": _opencode_agent_to_copilot_wrapper(_relative_to_repo(repo_root, agent_path), agent_path),
                "reason": "OpenCode agents need Copilot agent wrappers because the schemas differ.",
            })

        commands_root = repo_root / ".opencode" / "commands"
        for command_path in sorted(path for path in commands_root.glob("*.md") if path.is_file()):
            command_name = command_path.stem
            linked_destination = chosen_target / "skills" / command_name / "source-command.md"
            linked_destination_rel = _relative_to_repo(repo_root, linked_destination)
            collision = _destination_conflict(seen_destinations, linked_destination_rel, f"command source {command_name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": linked_destination_rel, "reason": collision})
            else:
                plan["actions"].append({
                    "action": "link",
                    "source": _relative_to_repo(repo_root, command_path),
                    "destination": linked_destination_rel,
                    "reason": "Keep the original OpenCode command markdown as a symlinked provenance file.",
                })
            wrapper_destination = chosen_target / "skills" / command_name / "SKILL.md"
            wrapper_destination_rel = _relative_to_repo(repo_root, wrapper_destination)
            collision = _destination_conflict(seen_destinations, wrapper_destination_rel, f"command wrapper {command_name}")
            if collision:
                plan["actions"].append({"action": "skip", "destination": wrapper_destination_rel, "reason": collision})
                continue
            plan["actions"].append({
                "action": "write-file",
                "destination": wrapper_destination_rel,
                "content": _command_to_skill_wrapper(_relative_to_repo(repo_root, command_path), command_path),
                "reason": "OpenCode commands need a Copilot SKILL.md wrapper that explains how to use the imported command template.",
            })

        for config_entry in inventory["opencode"]["config_files"]:
            translated_servers, skipped_servers = _translate_opencode_mcp_to_copilot(config_entry["data"])
            for skip in skipped_servers:
                plan["actions"].append({
                    "action": "skip",
                    "source": config_entry["path"],
                    "reason": f"MCP server {skip['server']}: {skip['reason']}",
                })
            if translated_servers:
                generated_mcp = True
                destination_rel = _relative_to_repo(repo_root, chosen_target / ".mcp.json")
                collision = _destination_conflict(seen_destinations, destination_rel, "copilot mcp")
                if collision:
                    plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
                else:
                    plan["actions"].append({
                        "action": "write-json",
                        "destination": destination_rel,
                        "data": {"servers": translated_servers},
                        "reason": "Translate local OpenCode MCP servers into Copilot .mcp.json format.",
                    })
                break

    plugin_json_path = chosen_target / "plugin.json"
    if not plugin_json_path.exists():
        plugin_name = chosen_target.name
        plugin_data: dict[str, Any] = {
            "name": plugin_name,
            "description": f"Bridge plugin generated from OpenCode sources in {repo_root.name}.",
            "version": "0.1.0",
            "keywords": ["bridge", "opencode", "copilot", "migration"],
            "skills": ["skills/"],
        }
        if generated_agents:
            plugin_data["agents"] = "agents/"
        if generated_mcp:
            plugin_data["mcpServers"] = ".mcp.json"
        destination_rel = _relative_to_repo(repo_root, plugin_json_path)
        collision = _destination_conflict(seen_destinations, destination_rel, "plugin manifest")
        if collision:
            plan["actions"].append({"action": "skip", "destination": destination_rel, "reason": collision})
        else:
            plan["actions"].append({
                "action": "write-json",
                "destination": destination_rel,
                "data": plugin_data,
                "reason": "Create a minimal Copilot plugin manifest for the generated bridge output.",
            })
    else:
        plan["actions"].append({
            "action": "skip",
            "destination": _relative_to_repo(repo_root, plugin_json_path),
            "reason": "plugin.json already exists at the target root; leaving the existing manifest in place.",
        })
    return plan


def _ensure_destination_within_repo(repo_root: Path, raw_destination: str | Path) -> Path:
    destination = Path(raw_destination)
    if not destination.is_absolute():
        destination = repo_root / destination
    resolved = destination.resolve(strict=False)
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Destination escapes repository root: {raw_destination}") from exc
    return destination


def _write_text_file(destination: Path, content: str) -> str:
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise FileExistsError(f"Refusing to overwrite symlink at {destination}")
        if destination.is_file():
            existing = destination.read_text(encoding="utf-8")
            if existing == content:
                return "kept"
            raise FileExistsError(f"Refusing to overwrite existing file at {destination}")
        raise FileExistsError(f"Refusing to overwrite existing path at {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return "written"


def _apply_link(repo_root: Path, source_rel: str, destination_rel: str) -> str:
    source = _safe_resolve_within_repo(repo_root, source_rel, must_exist=True)
    destination = _ensure_destination_within_repo(repo_root, destination_rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    relative_target = os.path.relpath(source, start=destination.parent)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            if destination.resolve(strict=False) == source.resolve():
                return "kept"
            raise FileExistsError(f"Refusing to replace existing symlink at {destination}")
        raise FileExistsError(f"Refusing to overwrite existing file at {destination}")
    os.symlink(relative_target, destination)
    return "linked"


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("status") != "ready":
        raise ValueError("Only plans with status 'ready' can be applied.")
    repo_root = Path(plan["repo_root"]).resolve()
    summary = {"linked": 0, "written": 0, "json_written": 0, "kept": 0, "skipped": 0}
    outcomes = []

    for action in plan.get("actions", []):
        kind = action["action"]
        if kind == "skip":
            summary["skipped"] += 1
            outcomes.append({"action": kind, "status": "skipped", **{k: v for k, v in action.items() if k != "action"}})
            continue
        if kind == "link":
            status = _apply_link(repo_root, action["source"], action["destination"])
            if status == "linked":
                summary["linked"] += 1
            else:
                summary["kept"] += 1
            outcomes.append({"action": kind, "status": status, "destination": action["destination"]})
            continue
        if kind in {"write-file", "write-json"}:
            destination = _ensure_destination_within_repo(repo_root, action["destination"])
            if kind == "write-json":
                content = json.dumps(action["data"], indent=2, sort_keys=True) + "\n"
            else:
                content = action["content"]
                if not content.endswith("\n"):
                    content += "\n"
            status = _write_text_file(destination, content)
            if status == "written":
                if kind == "write-json":
                    summary["json_written"] += 1
                else:
                    summary["written"] += 1
            else:
                summary["kept"] += 1
            outcomes.append({"action": kind, "status": status, "destination": action["destination"]})
            continue
        raise ValueError(f"Unsupported action type: {kind}")

    return {"repo_root": str(repo_root), "summary": summary, "outcomes": outcomes}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    scan_parser = subparsers.add_parser("scan", help="Inventory Copilot and OpenCode files in a repository.")
    scan_parser.add_argument("--repo-root", default=os.getcwd())

    plan_parser = subparsers.add_parser("plan", help="Generate a bridge plan without changing files.")
    plan_parser.add_argument("--repo-root", default=os.getcwd())
    plan_parser.add_argument("--source-root")
    plan_parser.add_argument("--target-root")
    plan_parser.add_argument("--target", required=True, choices=["copilot", "opencode"])

    apply_parser = subparsers.add_parser("apply", help="Apply a generated bridge plan directly.")
    apply_parser.add_argument("--repo-root", default=os.getcwd())
    apply_parser.add_argument("--source-root")
    apply_parser.add_argument("--target-root")
    apply_parser.add_argument("--target", required=True, choices=["copilot", "opencode"])

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "scan":
        result = inventory_repo(args.repo_root)
    elif args.subcommand == "plan":
        result = build_plan(args.repo_root, args.target, source_root=args.source_root, target_root=args.target_root)
    else:
        plan = build_plan(args.repo_root, args.target, source_root=args.source_root, target_root=args.target_root)
        result = {"plan": plan}
        if plan["status"] != "ready":
            result["error"] = "Plan is not ready to apply."
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1
        try:
            result["apply"] = apply_plan(plan)
        except (
            FileExistsError,
            FileNotFoundError,
            OSError,
            ValueError,
        ) as exc:
            result["error"] = str(exc)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
