"""Provide generalized build vocabulary and execution for httk manifests."""

import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from . import _manifest

DEFAULT_TAG = "any"
_PLATFORM_CACHE: dict[str, tuple[str, str]] = {}
_STDERR_TAIL = 1024

__all__ = [
    "DEFAULT_TAG",
    "BuildError",
    "BuildResult",
    "BuildSpec",
    "artifact_excluder",
    "execute_build",
    "overlay_artifacts",
    "platform_tag",
    "read_manifest_build_spec",
    "registered_generation",
    "write_generation",
]


@dataclass(frozen=True)
class BuildSpec:
    """Describe a build command and its disposable artifacts.

    :param command: Supply the build command.
    :param artifacts: Name artifact patterns to exclude from source publication.
    :param platform: Restrict the build to a platform, when supplied.
    """

    command: str
    artifacts: tuple[str, ...]
    platform: str | None = None


class BuildError(ValueError):
    """Describe a build failure with its protocol code.

    :param code: Identify the build failure.
    :param message: Describe the build failure.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BuildResult:
    """Describe the result of executing a build.

    :param tag: Identify the platform registration tag.
    :param platform_output: Preserve the raw platform probe output.
    :param artifact_files: Name the collected artifact files as relative POSIX paths.
    """

    tag: str
    platform_output: str
    artifact_files: tuple[str, ...]


def _build_section(
    table: Mapping[str, object], root: Path, build_path: str, protected_names: Sequence[str]
) -> BuildSpec | None:
    if "build" not in table:
        return None
    build = _manifest.require_table(table["build"], build_path, root)
    _manifest.reject_unknown(build, {"command", "platform", "artifacts"}, build_path, root)
    command = _manifest.require_string(build, "command", build_path, root, required=True)
    assert command is not None
    platform = _manifest.optional_string(build, "platform", build_path, root)
    for key, value in (("command", command), ("platform", platform)):
        if value is None:
            continue
        try:
            argv = shlex.split(value)
        except ValueError as exc:
            raise _manifest.manifest_error(root, f"{build_path}.{key} must contain valid shell words: {exc}") from exc
        if not argv:
            raise _manifest.manifest_error(root, f"{build_path}.{key} must contain at least one shell word")
    raw_artifacts = build.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise _manifest.manifest_error(root, f"{build_path}.artifacts must be a nonempty array of patterns")
    artifacts: list[str] = []
    protected = tuple(protected_names)
    for pattern in raw_artifacts:
        if not isinstance(pattern, str) or not pattern:
            raise _manifest.manifest_error(root, f"{build_path}.artifacts must contain only nonempty strings")
        if pattern.startswith("/") or "\\" in pattern or any(part in {".", ".."} for part in pattern.split("/")):
            raise _manifest.manifest_error(
                root,
                f"{build_path}.artifacts pattern {pattern!r} must be relative and contain no '.', '..', or backslashes",
            )
        if any(fnmatch.fnmatchcase(name, pattern) for name in protected):
            if protected == ("run", "httk_workflow.toml"):
                message = (
                    f"{build_path}.artifacts pattern {pattern!r} would strip the runner entry point or manifest "
                    "from publication; 'run' and 'httk_workflow.toml' must remain available"
                )
            else:
                names = " and ".join(repr(name) for name in protected)
                message = f"{build_path}.artifacts pattern {pattern!r} would strip protected names; {names} must remain available"
            raise _manifest.manifest_error(root, message)
        artifacts.append(pattern)
    return BuildSpec(command=command, platform=platform, artifacts=tuple(artifacts))


def read_manifest_build_spec(
    root: Path, *, manifest_name: str, table_name: str, protected_names: Sequence[str]
) -> BuildSpec | None:
    """Read and validate the optional build table in a manifest.

    :param root: Locate the manifest directory.
    :param manifest_name: Name the manifest file.
    :param table_name: Name the top-level manifest table.
    :param protected_names: Name members artifact patterns must preserve.
    :return: The build specification, or ``None`` when absent.
    :raises ValueError: If the manifest or build table is malformed.
    """

    manifest = root / manifest_name
    if not manifest.is_file():
        return None
    raw = _manifest.load_manifest_toml(manifest, root)
    table = raw.get(table_name)
    if table is None:
        return None
    return _build_section(
        _manifest.require_table(table, f"[{table_name}]", root), root, f"[{table_name}.build]", protected_names
    )


def artifact_excluder(spec: BuildSpec | None) -> Callable[[str], bool]:
    """Return a predicate for declared artifacts and their descendants.

    :param spec: Supply the build specification, when present.
    :return: A predicate accepting relative POSIX paths.
    """

    if spec is None:
        return lambda path: False

    def excluded(path: str) -> bool:
        parts = PurePosixPath(path).parts
        return any(
            fnmatch.fnmatchcase("/".join(parts[:index]), pattern)
            for index in range(1, len(parts) + 1)
            for pattern in spec.artifacts
        )

    return excluded


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _clean_environment(strip_env_prefixes: Sequence[str], keep_env: Sequence[str]) -> dict[str, str]:
    keep = set(keep_env)
    return {
        key: value
        for key, value in os.environ.items()
        if key in keep or not any(key.startswith(prefix) for prefix in strip_env_prefixes)
    }


def platform_tag(platform_command: str | None) -> tuple[str, str]:
    """Probe and tag the current platform.

    :param platform_command: Supply the platform probe command, when present.
    :return: The sanitized tag and the probe's raw standard output.
    :raises BuildError: If the platform probe cannot be run successfully.
    """

    if platform_command is None:
        return DEFAULT_TAG, ""
    cached = _PLATFORM_CACHE.get(platform_command)
    if cached is not None:
        return cached
    try:
        argv = shlex.split(platform_command)
        if not argv:
            raise ValueError("empty command")
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    except (OSError, ValueError) as exc:
        raise BuildError("runner_build_failed", f"platform probe {platform_command!r} failed: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr[-_STDERR_TAIL:].strip()
        detail = f"; stderr: {stderr}" if stderr else ""
        raise BuildError(
            "runner_build_failed",
            f"platform probe {platform_command!r} failed with exit code {completed.returncode}{detail}",
        )
    raw = completed.stdout
    value = raw.strip()
    digest = hashlib.sha256(raw.encode()).hexdigest()
    tag = re.sub(r"[^A-Za-z0-9._-]", "-", value)
    if not tag or tag in {".", ".."} or len(tag) > 64:
        tag = "h" + digest[:16]
    else:
        tag = f"{tag}.{digest[:8]}"
    result = tag, raw
    _PLATFORM_CACHE[platform_command] = result
    return result


def _write_build_log(path: Path, *, command: str, cwd: Path, exit_code: int, platform_output: str, output: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                f"command: {command}",
                f"cwd: {cwd}",
                f"exit code: {exit_code}",
                f"platform output: {platform_output!r}",
                "build output:",
                output.rstrip("\n"),
            )
        )
        + "\n",
        encoding="utf-8",
    )


def execute_build(
    source: Path,
    spec: BuildSpec,
    *,
    strip_env_prefixes: Sequence[str],
    keep_env: Sequence[str] = (),
    log_path: Path | None = None,
) -> BuildResult:
    """Execute a build and collect its declared artifacts.

    :param source: Run the build from this source directory.
    :param spec: Describe the build command and artifact patterns.
    :param strip_env_prefixes: Remove environment variables with these prefixes.
    :param keep_env: Preserve these variable names despite their prefixes.
    :param log_path: Optionally capture build output and metadata at this path.
    :return: The platform tag, probe output, and collected artifact paths.
    :raises BuildError: If probing, execution, or artifact collection fails.
    """

    tag, platform_output = platform_tag(spec.platform)
    try:
        argv = shlex.split(spec.command)
        if not argv:
            raise ValueError("empty command")
    except ValueError as exc:
        raise BuildError("runner_build_failed", f"build command {spec.command!r} is invalid: {exc}") from exc

    output = ""
    exit_code = -1
    try:
        completed = subprocess.run(
            argv,
            cwd=source,
            env=_clean_environment(strip_env_prefixes, keep_env),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output = completed.stdout
        exit_code = completed.returncode
    except OSError as exc:
        if log_path is not None:
            _write_build_log(
                log_path,
                command=spec.command,
                cwd=source,
                exit_code=exit_code,
                platform_output=platform_output,
                output=output,
            )
        raise BuildError("runner_build_failed", f"build command {spec.command!r} failed: {exc}") from exc
    if log_path is not None:
        _write_build_log(
            log_path,
            command=spec.command,
            cwd=source,
            exit_code=exit_code,
            platform_output=platform_output,
            output=output,
        )
    if exit_code != 0:
        tail = output[-_STDERR_TAIL:].strip()
        detail = f"; output tail: {tail}" if tail else ""
        raise BuildError(
            "runner_build_failed",
            f"build command {spec.command!r} failed with exit code {exit_code}{detail}",
        )

    predicate = artifact_excluder(spec)
    matches: list[str] = []
    for entry in source.rglob("*"):
        relative = entry.relative_to(source).as_posix()
        if not predicate(relative):
            continue
        if entry.is_symlink():
            raise BuildError("runner_build_failed", f"build produced symlink artifact: {relative}")
        if entry.is_file():
            matches.append(relative)
    if not matches:
        raise BuildError(
            "runner_build_failed",
            f"build command {spec.command!r} produced no artifacts matching {spec.artifacts!r}",
        )
    return BuildResult(tag, platform_output, tuple(sorted(matches)))


def _safe_registration_path(value: str, *, allow_nested: bool) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and (allow_nested or path.name == value)
    )


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_generation(
    builds_root: Path,
    relative: str,
    tag: str,
    source: Path,
    artifact_files: Sequence[str],
    stamp: Mapping[str, object],
) -> Path:
    """Copy build artifacts into an atomically registered generation.

    :param builds_root: Locate the build registration store.
    :param relative: Identify the source registration relative to the store.
    :param tag: Identify the platform registration.
    :param source: Locate the built source tree.
    :param artifact_files: Name relative POSIX artifact files to copy.
    :param stamp: Supply the build stamp fields.
    :return: The new generation directory.
    """

    if not _safe_registration_path(relative, allow_nested=True) or not _safe_registration_path(tag, allow_nested=False):
        raise ValueError("invalid build registration path")
    tag_root = builds_root / relative / tag
    tag_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".gen-", dir=tag_root))
    generation_name = f"gen-{uuid.uuid4()}"
    generation = tag_root / generation_name
    try:
        artifacts_root = temporary / "artifacts"
        for artifact_file in artifact_files:
            if not _safe_registration_path(artifact_file, allow_nested=True):
                raise ValueError(f"invalid artifact path: {artifact_file!r}")
            source_file = source / PurePosixPath(artifact_file)
            if source_file.is_symlink() or not source_file.is_file():
                raise ValueError(f"artifact is not a regular file: {artifact_file}")
            destination = artifacts_root / PurePosixPath(artifact_file)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
        _write_json_atomic(temporary / "build.json", {**stamp, "built_at": _utc_now()})
        os.replace(temporary, generation)
        _write_json_atomic(tag_root / "current.json", {"generation": generation_name})
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return generation


def registered_generation(
    builds_root: Path,
    relative: str,
    tag: str,
    *,
    format_name: str,
    expected_source_sha256: str,
) -> Path | None:
    """Return registered artifacts when the build stamp still matches.

    :param builds_root: Locate the build registration store.
    :param relative: Identify the source registration relative to the store.
    :param tag: Identify the platform registration.
    :param format_name: Require this build stamp format name.
    :param expected_source_sha256: Require this source digest.
    :return: The registered artifact directory, or ``None`` when unusable.
    """

    if not _safe_registration_path(relative, allow_nested=True) or not _safe_registration_path(tag, allow_nested=False):
        return None
    root = builds_root / relative / tag
    try:
        pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    generation_name = pointer.get("generation") if isinstance(pointer, dict) else None
    if not isinstance(generation_name, str) or not generation_name.startswith("gen-"):
        return None
    generation = root / generation_name
    if generation.parent != root or not generation.is_dir():
        return None
    artifacts = generation / "artifacts"
    stamp = generation / "build.json"
    if not artifacts.is_dir() or not stamp.is_file():
        return None
    try:
        value = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("format") != format_name or value.get("format_version") != 1:
        return None
    if value.get("source_sha256") != expected_source_sha256:
        return None
    return artifacts


def overlay_artifacts(artifacts_dir: Path, target: Path) -> None:
    """Copy registered artifact files over a staged tree.

    :param artifacts_dir: Locate the registered artifact tree.
    :param target: Locate the staged tree to overlay.
    """

    for entry in artifacts_dir.rglob("*"):
        if entry.is_file():
            destination = target / entry.relative_to(artifacts_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, destination)
