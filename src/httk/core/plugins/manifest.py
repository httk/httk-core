"""Parse and validate installed httk plugin manifests."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .._manifest import (
    load_manifest_toml,
    manifest_error,
    member_path,
    optional_string,
    reject_unknown,
    require_string,
    require_table,
)
from ..building import BuildSpec, artifact_excluder, read_manifest_build_spec

PLUGIN_MANIFEST = "httk_plugin.toml"
_NAME_RE = re.compile(r"[a-z0-9._-]+")

__all__ = ["PLUGIN_MANIFEST", "PluginManifest", "PluginProgram", "parse_plugin_manifest"]


@dataclass(frozen=True)
class PluginProgram:
    """Describe one declared plugin program.

    :param name: Name the program and its shim.
    :param file: Name the program member relative to the plugin root.
    :param description: Describe the program, when supplied.
    """

    name: str
    file: str
    description: str | None


@dataclass(frozen=True)
class PluginManifest:
    """Describe a validated plugin manifest.

    :param name: Name the plugin.
    :param description: Describe the plugin, when supplied.
    :param templates: Name project-template directories.
    :param workflows: Name workflow-package directories.
    :param programs: Describe declared utility programs.
    :param build: Describe the optional build.
    :param root: Locate the parsed plugin directory.
    """

    name: str
    description: str | None
    templates: tuple[str, ...]
    workflows: tuple[str, ...]
    programs: tuple[PluginProgram, ...]
    build: BuildSpec | None
    root: Path


def _name(value: object, path: str, directory: Path) -> str:
    name = require_string({"name": value}, "name", path, directory, required=True)
    assert name is not None
    if _NAME_RE.fullmatch(name) is None or name in {".", ".."} or name.startswith("-"):
        raise manifest_error(directory, f"{path}.name must match [a-z0-9._-]+, without '.'/'..' or a leading '-'")
    return name


def _directories(plugin: Mapping[str, object], key: str, filename: str, directory: Path) -> tuple[str, ...]:
    raw = plugin.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise manifest_error(directory, f"[plugin].{key} must be an array")
    members: list[str] = []
    for index, value in enumerate(raw):
        path = f"[plugin].{key}[{index}]"
        member = member_path(directory, value, path, directory_ok=True)
        if member in members:
            raise manifest_error(directory, f"[plugin].{key} contains duplicate directory {member!r}")
        marker = directory.joinpath(*PurePosixPath(member).parts) / filename
        if marker.is_symlink() or not marker.is_file():
            # Full template/workflow validation is wired at install time later.
            raise manifest_error(directory, f"{path} must contain regular file {filename!r}")
        members.append(member)
    return tuple(members)


def _overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    return left_parts[: len(right_parts)] == right_parts or right_parts[: len(left_parts)] == left_parts


def _programs(plugin: Mapping[str, object], directory: Path, build: BuildSpec | None) -> tuple[PluginProgram, ...]:
    raw = plugin.get("programs")
    if raw is None:
        return ()
    programs = require_table(raw, "[plugin.programs]", directory)
    result: list[PluginProgram] = []
    excluded = artifact_excluder(build)
    for name, value in programs.items():
        program_name = _name(name, f"[plugin.programs.{name}]", directory)
        path = f"[plugin.programs.{program_name}]"
        table = require_table(value, path, directory)
        reject_unknown(table, {"file", "description"}, path, directory)
        member = member_path(directory, table.get("file"), f"{path}.file", must_exist=False)
        candidate = directory.joinpath(*PurePosixPath(member).parts)
        if build is None or not excluded(member) or (candidate.exists() and not candidate.is_file()):
            member_path(directory, member, f"{path}.file")
        description = optional_string(table, "description", path, directory)
        result.append(PluginProgram(program_name, member, description))
    return tuple(result)


def parse_plugin_manifest(directory: Path) -> PluginManifest:
    """Parse and validate one plugin manifest.

    :param directory: Locate the plugin directory.
    :return: The validated plugin manifest.
    :raises ValueError: If the plugin directory or manifest is malformed.
    """

    root = Path(directory).expanduser()
    if not root.is_dir() or root.is_symlink():
        raise manifest_error(root, "plugin directory must be a directory")
    raw = load_manifest_toml(root / PLUGIN_MANIFEST, root)
    reject_unknown(raw, {"plugin"}, "", root)
    plugin = require_table(raw.get("plugin"), "[plugin]", root)
    reject_unknown(plugin, {"name", "description", "templates", "workflows", "programs", "build"}, "[plugin]", root)
    name = _name(plugin.get("name"), "[plugin]", root)
    description = optional_string(plugin, "description", "[plugin]", root)
    build = read_manifest_build_spec(
        root,
        manifest_name=PLUGIN_MANIFEST,
        table_name="plugin",
        protected_names=(PLUGIN_MANIFEST,),
    )
    templates = _directories(plugin, "templates", "httk_project_template.toml", root)
    workflows = _directories(plugin, "workflows", "httk_workflow.toml", root)
    all_directories = [("template", member) for member in templates] + [("workflow", member) for member in workflows]
    for index, (left_kind, left) in enumerate(all_directories):
        for right_kind, right in all_directories[index + 1 :]:
            if _overlap(left, right):
                raise manifest_error(
                    root,
                    f"{left_kind} directory {left!r} overlaps {right_kind} directory {right!r}",
                )
    programs = _programs(plugin, root, build)
    return PluginManifest(name, description, templates, workflows, programs, build, root)
