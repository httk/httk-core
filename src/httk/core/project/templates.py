"""Parse, resolve, and instantiate httk project templates."""

import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .._manifest import (
    executable_member,
    load_manifest_toml,
    manifest_error,
    matches_json_type,
    member_path,
    optional_string,
    reject_unknown,
    require_string,
    require_table,
)
from ..plugins.installed import InstalledPlugin, installed_plugins

TEMPLATE_MANIFEST = "httk_project_template.toml"
_ID_RE = re.compile(r"[a-z0-9._-]+")
_PARAMETER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PARAMETER_TYPES = {"string", "number", "integer", "boolean", "array", "object"}
_LOGGER = logging.getLogger(__name__)

__all__ = [
    "TEMPLATE_MANIFEST",
    "ProjectTemplate",
    "TemplateInstantiateRequest",
    "TemplateParameter",
    "available_templates",
    "check_parameters",
    "instantiate_template",
    "parse_template_manifest",
    "resolve_template",
    "template_instantiate_main",
]


@dataclass(frozen=True)
class TemplateParameter:
    """Describe one template instantiate parameter."""

    name: str
    type: str
    description: str | None
    default: object | None
    has_default: bool


@dataclass(frozen=True)
class ProjectTemplate:
    """Describe a validated project template."""

    id: str
    description: str | None
    files: tuple[str, ...]
    instantiate_file: str | None
    parameters: tuple[TemplateParameter, ...]
    root: Path


@dataclass(frozen=True)
class TemplateInstantiateRequest:
    """Describe the request received by a template instantiate hook."""

    template: str
    parameters: Mapping[str, object]
    project: Mapping[str, object]


def _is_json_value(value: object, active: set[int] | None = None) -> bool:
    """Return whether *value* is a finite, recursively JSON-compatible value."""

    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if not isinstance(value, (list, dict)):
        return False
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        return False
    active.add(identity)
    try:
        if isinstance(value, list):
            return all(_is_json_value(item, active) for item in value)
        return all(isinstance(key, str) and _is_json_value(item, active) for key, item in value.items())
    finally:
        active.remove(identity)


def _overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    return left_parts[: len(right_parts)] == right_parts or right_parts[: len(left_parts)] == left_parts


def _template_id(value: object, directory: Path) -> str:
    template_id = require_string({"id": value}, "id", "[template]", directory, required=True)
    assert template_id is not None
    if _ID_RE.fullmatch(template_id) is None or template_id in {".", ".."} or template_id.startswith("-"):
        raise manifest_error(directory, "[template].id must match [a-z0-9._-]+, without '.'/'..' or a leading '-'")
    return template_id


def _template_files(template: Mapping[str, object], directory: Path, instantiate_file: str | None) -> tuple[str, ...]:
    raw = template.get("files")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise manifest_error(directory, "[template].files must be an array")
    files: list[str] = []
    for index, value in enumerate(raw):
        path = f"[template].files[{index}]"
        member = member_path(directory, value, path, directory_ok=True)
        if member == TEMPLATE_MANIFEST or member == instantiate_file:
            raise manifest_error(directory, f"{path} may not list a protected template member {member!r}")
        if member in files:
            raise manifest_error(directory, f"[template].files contains duplicate member {member!r}")
        if any(_overlap(member, other) for other in files):
            raise manifest_error(
                directory, f"[template].files contains overlapping members {member!r} and another entry"
            )
        files.append(member)
    return tuple(files)


def _template_parameters(
    template: Mapping[str, object], directory: Path, has_hook: bool
) -> tuple[TemplateParameter, ...]:
    raw = template.get("parameters")
    if raw is None:
        return ()
    parameters = require_table(raw, "[template.parameters]", directory)
    result: list[TemplateParameter] = []
    for name, value in parameters.items():
        path = f"[template.parameters.{name}]"
        if _PARAMETER_RE.fullmatch(name) is None:
            raise manifest_error(directory, f"{path} has an invalid parameter name")
        table = require_table(value, path, directory)
        reject_unknown(table, {"type", "description", "default"}, path, directory)
        parameter_type = require_string(table, "type", path, directory, required=True)
        assert parameter_type is not None
        if parameter_type not in _PARAMETER_TYPES:
            raise manifest_error(directory, f"{path}.type must be one of: {', '.join(sorted(_PARAMETER_TYPES))}")
        description = optional_string(table, "description", path, directory)
        has_default = "default" in table
        default = table.get("default")
        if has_default:
            if not _is_json_value(default):
                raise manifest_error(directory, f"{path}.default must contain only finite JSON values")
            if not matches_json_type(default, parameter_type):
                raise manifest_error(directory, f"{path}.default does not match type {parameter_type!r}")
        result.append(TemplateParameter(name, parameter_type, description, default, has_default))
    if result and not has_hook:
        raise manifest_error(directory, "template declares parameters but no [template.instantiate] hook consumes them")
    return tuple(result)


def parse_template_manifest(directory: Path) -> ProjectTemplate:
    """Parse and validate one project-template manifest.

    :param directory: Locate the template directory.
    :return: The validated project template.
    :raises ValueError: If the template directory or manifest is malformed.
    """

    root = Path(directory).expanduser()
    if not root.is_dir() or root.is_symlink():
        raise manifest_error(root, "template directory must be a directory")
    raw = load_manifest_toml(root / TEMPLATE_MANIFEST, root)
    reject_unknown(raw, {"template"}, "", root)
    template = require_table(raw.get("template"), "[template]", root)
    reject_unknown(template, {"id", "description", "files", "instantiate", "parameters"}, "[template]", root)
    template_id = _template_id(template.get("id"), root)
    description = optional_string(template, "description", "[template]", root)

    instantiate_file: str | None = None
    if "instantiate" in template:
        instantiate = require_table(template["instantiate"], "[template.instantiate]", root)
        reject_unknown(instantiate, {"file"}, "[template.instantiate]", root)
        instantiate_file, _ = executable_member(root, instantiate.get("file"), "[template.instantiate].file")

    files = _template_files(template, root, instantiate_file)
    parameters = _template_parameters(template, root, instantiate_file is not None)
    return ProjectTemplate(template_id, description, files, instantiate_file, parameters, root)


def available_templates() -> tuple[tuple[str, ProjectTemplate], ...]:
    """Return all valid templates from installed plugins, sorted by name and id."""

    result: list[tuple[str, ProjectTemplate]] = []
    for plugin in installed_plugins():
        for member in plugin.manifest.templates:
            try:
                template = parse_template_manifest(plugin.root / PurePosixPath(member))
            except (OSError, ValueError) as exc:
                _LOGGER.warning("Skipping template %r from plugin %s: %s", member, plugin.name, exc)
                continue
            result.append((plugin.name, template))
    return tuple(sorted(result, key=lambda item: (item[0], item[1].id)))


def _plugin_templates(plugin: InstalledPlugin) -> tuple[ProjectTemplate, ...]:
    return tuple(parse_template_manifest(plugin.root / PurePosixPath(member)) for member in plugin.manifest.templates)


def resolve_template(selector: str) -> ProjectTemplate:
    """Resolve a template path, qualified plugin selector, or bare template id.

    :param selector: Select an explicit directory, ``plugin:id``, or bare id.
    :return: The selected project template.
    :raises ValueError: If the selector cannot identify exactly one template.
    """

    candidate = Path(selector).expanduser()
    if (
        "/" in selector
        or os.sep in selector
        or selector.startswith(".")
        or (candidate.is_dir() and (candidate / TEMPLATE_MANIFEST).is_file())
    ):
        return parse_template_manifest(candidate)

    if selector.count(":") == 1:
        plugin_name, template_id = selector.split(":")
        for plugin in installed_plugins():
            if plugin.name != plugin_name:
                continue
            for template in _plugin_templates(plugin):
                if template.id == template_id:
                    return template
            raise ValueError(f"plugin {plugin_name!r} has no template {template_id!r}")
        raise ValueError(f"plugin {plugin_name!r} is not installed")

    matches = [(plugin, template) for plugin, template in available_templates() if template.id == selector]
    if len(matches) == 1:
        return matches[0][1]
    if len(matches) > 1:
        qualified = ", ".join(f"{plugin}:{template.id}" for plugin, template in matches)
        raise ValueError(f"template id {selector!r} is ambiguous; use one of: {qualified}")
    known = ", ".join(f"{plugin}:{template.id}" for plugin, template in available_templates()) or "none"
    raise ValueError(f"unknown template id {selector!r}; known templates: {known}")


def check_parameters(template: ProjectTemplate, supplied: Mapping[str, object]) -> dict[str, object]:
    """Validate supplied parameters and apply declared defaults.

    :param template: Validate against this template's declaration.
    :param supplied: Supply user parameter values.
    :return: Supplied values combined with optional defaults.
    :raises ValueError: If names or values do not match the declaration.
    """

    declared = {parameter.name: parameter for parameter in template.parameters}
    undeclared = sorted(set(supplied) - set(declared))
    if undeclared:
        raise ValueError(f"template declares no parameters named: {', '.join(repr(name) for name in undeclared)}")
    for name, value in supplied.items():
        parameter = declared[name]
        if not _is_json_value(value):
            raise ValueError(f"template parameter {name!r} must contain only finite JSON values")
        if not matches_json_type(value, parameter.type):
            raise ValueError(
                f"template parameter {name!r} does not match type {parameter.type!r}; got {type(value).__name__}. "
                "Supply a matching value — note that a command-line NAME=VALUE parses VALUE as JSON when it can, "
                "so quote a literal string as NAME='\"text\"'"
            )
    missing = [
        parameter.name
        for parameter in template.parameters
        if not parameter.has_default and parameter.name not in supplied
    ]
    if missing:
        raise ValueError(f"missing mandatory template parameters: {', '.join(missing)}")
    checked = dict(supplied)
    for parameter in template.parameters:
        if parameter.has_default and parameter.name not in checked:
            checked[parameter.name] = parameter.default
    return checked


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _source_entries(source: Path, destination: Path) -> list[tuple[Path, Path, bool]]:
    entries: list[tuple[Path, Path, bool]] = []
    if source.is_file():
        return [(source, destination, True)]
    entries.append((source, destination, False))
    for entry in sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix()):
        if entry.is_symlink():
            raise ValueError(f"template member contains forbidden symlink: {entry}")
        if entry.is_dir():
            entries.append((entry, destination / entry.relative_to(source), False))
        elif entry.is_file():
            entries.append((entry, destination / entry.relative_to(source), True))
        else:
            raise ValueError(f"template member contains forbidden special file: {entry}")
    return entries


def _destination_conflict(project_root: Path, destination: Path, is_file: bool) -> str | None:
    relative = destination.relative_to(project_root)
    current = project_root
    for part in relative.parts:
        current /= part
        if _lexists(current) and (
            current.is_symlink()
            or (current == destination and not current.is_dir())
            or (current != destination and not current.is_dir())
        ):
            return current.relative_to(project_root).as_posix()
    if is_file and _lexists(destination):
        return relative.as_posix()
    return None


def _copy_members(template: ProjectTemplate, project_root: Path) -> None:
    entries: list[tuple[Path, Path, bool]] = []
    for member in template.files:
        source = template.root.joinpath(*PurePosixPath(member).parts)
        entries.extend(_source_entries(source, project_root / Path(*PurePosixPath(member).parts)))
    collisions = sorted(
        {
            collision
            for _, destination, is_file in entries
            if (collision := _destination_conflict(project_root, destination, is_file))
        }
    )
    if collisions:
        raise ValueError(f"template copy collides with existing project members: {', '.join(collisions)}")
    for member in template.files:
        source = template.root.joinpath(*PurePosixPath(member).parts)
        destination = project_root.joinpath(*PurePosixPath(member).parts)
        if source.is_dir():
            shutil.copytree(source, destination, copy_function=shutil.copy2, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def _stderr_excerpt(stderr: str | bytes | None) -> str:
    if isinstance(stderr, bytes):
        stderr = stderr.decode(errors="replace")
    return (stderr or "").strip()[-1000:]


def _run_hook(
    template: ProjectTemplate,
    project_root: Path,
    parameters: Mapping[str, object],
    project_info: Mapping[str, object],
    timeout: float,
) -> tuple[str, ...]:
    assert template.instantiate_file is not None
    hook_path = (template.root / Path(*PurePosixPath(template.instantiate_file).parts)).resolve()
    request = {
        "format": "httk-project-template-instantiate",
        "format_version": 2,
        "template": template.id,
        "parameters": dict(parameters),
        "project": {**project_info, "root": str(project_root)},
    }
    environment = dict(os.environ)
    for variable in tuple(environment):
        if variable.startswith("HTTK_") and variable not in {"HTTK_CONFIG_HOME", "HTTK_DATA_HOME"}:
            environment.pop(variable)
    command = [sys.executable, str(hook_path)] if hook_path.suffix == ".py" else [str(hook_path)]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(request, separators=(",", ":"), allow_nan=False),
            capture_output=True,
            text=True,
            cwd=project_root,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        excerpt = _stderr_excerpt(exc.stderr)
        detail = f" (stderr: {excerpt})" if excerpt else ""
        raise ValueError(f"template instantiate hook {template.instantiate_file!r} timed out{detail}") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"cannot run template instantiate hook {template.instantiate_file!r}: {exc}") from exc
    excerpt = _stderr_excerpt(completed.stderr)
    detail = f" (stderr: {excerpt})" if excerpt else ""
    if completed.returncode != 0:
        raise ValueError(
            f"template instantiate hook {template.instantiate_file!r} failed with exit {completed.returncode}{detail}"
        )
    try:
        response = json.loads(completed.stdout)
        if not isinstance(response, Mapping):
            raise ValueError("response is not a JSON object")
        if "notes" not in response:
            return ()
        notes = response["notes"]
        if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
            raise ValueError("response notes must be an array of strings")
        return tuple(notes)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"template instantiate hook {template.instantiate_file!r} returned invalid JSON: {exc}{detail}"
        ) from exc


def instantiate_template(
    template: ProjectTemplate,
    project_root: Path,
    parameters: Mapping[str, object],
    *,
    project_info: Mapping[str, object],
    timeout: float = 3600.0,
) -> tuple[str, ...]:
    """Copy a template into an initialized project and run its optional hook.

    :param template: Instantiate this validated template.
    :param project_root: Initialized project root to populate.
    :param parameters: Supply template parameter values.
    :param project_info: Supply project metadata for the hook request.
    :param timeout: Limit hook execution time in seconds.
    :return: Hook notes, or an empty tuple when no notes are returned.
    :raises ValueError: If validation, copying, or hook execution fails.
    """

    root = Path(project_root).expanduser().resolve()
    checked = check_parameters(template, parameters)
    _copy_members(template, root)
    if template.instantiate_file is None:
        return ()
    return _run_hook(template, root, checked, project_info, timeout)


def template_instantiate_main(
    fn: Callable[[TemplateInstantiateRequest], Mapping[str, object] | None],
) -> None:
    """Run a template hook function using the v1 JSON stdin/stdout protocol.

    :param fn: Handle the decoded template instantiate request.
    :return: Nothing; the response is written as one JSON document.
    """

    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, Mapping):
            raise ValueError("template instantiate request must be a JSON object")
        if request.get("format") != "httk-project-template-instantiate" or request.get("format_version") != 2:
            raise ValueError("invalid template instantiate request envelope")
        template = request.get("template")
        parameters = request.get("parameters")
        project = request.get("project")
        if not isinstance(template, str) or not isinstance(parameters, Mapping) or not isinstance(project, Mapping):
            raise ValueError("template instantiate request has invalid template, parameters, or project")
        response = fn(TemplateInstantiateRequest(template, parameters, project))
        if response is None:
            response = {}
        if not isinstance(response, Mapping):
            raise TypeError("template instantiate hook must return a mapping or None")
        print(json.dumps(dict(response), separators=(",", ":"), allow_nan=False), flush=True)
    except Exception as exc:
        raise SystemExit(str(exc) or type(exc).__name__) from exc
