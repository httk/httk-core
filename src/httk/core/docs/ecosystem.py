"""Discover and validate the module pins used by the aggregate documentation site."""

import json
import os
import subprocess
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path

from .semver import VersionError, parse_tag

__all__ = [
    "EcosystemManifestError",
    "build_ecosystem_manifest",
    "read_ecosystem_manifest",
    "verify_ecosystem_manifest",
    "write_ecosystem_manifest",
]


class EcosystemManifestError(RuntimeError):
    """Raised when an ecosystem checkout cannot produce a valid manifest."""


def _git(repository: Path, arguments: list[str]) -> str:
    result = _git_result(repository, arguments)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise EcosystemManifestError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def _git_result(repository: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_SYSTEM"] = os.devnull
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise EcosystemManifestError("git is not available on PATH") from exc
    return result


def _expected_checkouts(submodules_dir: Path) -> tuple[Path, dict[str, Path]]:
    """Read the superproject's direct submodule paths and their gitlink entries."""

    root = Path(_git(submodules_dir, ["rev-parse", "--show-toplevel"])).resolve()
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        raise EcosystemManifestError(f"superproject has no .gitmodules: {gitmodules}")
    result = _git_result(
        root,
        ["config", "--file", str(gitmodules), "--get-regexp", r"^submodule\..*\.path$"],
    )
    if result.returncode not in {0, 1}:
        detail = (result.stderr or result.stdout).strip()
        raise EcosystemManifestError(f"cannot read submodule paths from {gitmodules}: {detail}")
    expected: dict[str, Path] = {}
    for line in result.stdout.splitlines():
        _key, value = line.split(None, 1)
        configured = Path(value.strip())
        if configured.is_absolute():
            raise EcosystemManifestError(f"submodule path must be relative: {configured}")
        checkout = root / configured
        try:
            relative = checkout.relative_to(submodules_dir)
        except ValueError as exc:
            raise EcosystemManifestError(f"submodule path is outside {submodules_dir}: {configured}") from exc
        if len(relative.parts) != 1:
            raise EcosystemManifestError(f"submodule path is not a direct child of {submodules_dir}: {configured}")
        name = relative.name
        if name in expected:
            raise EcosystemManifestError(f"duplicate submodule checkout name: {name}")
        expected[name] = checkout
    if not expected:
        raise EcosystemManifestError(f"superproject declares no submodules in {gitmodules}")
    return root, expected


def _gitlink_object_id(root: Path, checkout: Path) -> str | None:
    relative = checkout.relative_to(root).as_posix()
    result = _git_result(root, ["ls-files", "-s", "--", relative])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    rows = [line.split(maxsplit=3) for line in result.stdout.splitlines()]
    if len(rows) != 1 or len(rows[0]) != 4 or rows[0][0] != "160000":
        return None
    return rows[0][1]


def _exact_release_tag(repository: Path) -> str | None:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_SYSTEM"] = os.devnull
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "describe", "--exact-match", "--tags", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise EcosystemManifestError("git is not available on PATH") from exc
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    try:
        parse_tag(tag)
    except VersionError:
        return None
    return tag


def _distribution_version(repository: Path) -> str | None:
    path = repository / "pyproject.toml"
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = document.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) and version else None


def build_ecosystem_manifest(
    submodules_dir: str | Path,
    *,
    require_release_tags: bool = False,
) -> dict[str, object]:
    """Build the sorted manifest for direct Git checkouts under *submodules_dir*."""

    directory = Path(submodules_dir).expanduser().resolve()
    if not directory.is_dir():
        raise EcosystemManifestError(f"submodules directory does not exist: {directory}")
    root, expected = _expected_checkouts(directory)
    actual_directories = {path.name for path in directory.iterdir() if path.is_dir()}
    unexpected = sorted(actual_directories - set(expected))
    if unexpected:
        raise EcosystemManifestError("unexpected checkout directories: " + ", ".join(unexpected))
    modules: dict[str, dict[str, str | None]] = {}
    for name in sorted(expected):
        checkout = expected[name]
        if not checkout.is_dir():
            raise EcosystemManifestError(f"expected module checkout is missing: {checkout}")
        if not (checkout / ".git").exists():
            raise EcosystemManifestError(f"expected module checkout is not a Git checkout: {checkout}")
        gitlink = _gitlink_object_id(root, checkout)
        if gitlink is None:
            raise EcosystemManifestError(f"submodule path is not a gitlink: {checkout}")
        head = _git(checkout, ["rev-parse", "HEAD"])
        if gitlink != head:
            raise EcosystemManifestError(f"gitlink mismatch for {name}: index {gitlink}, checkout HEAD {head}")
        tag = _exact_release_tag(checkout)
        distribution_version = _distribution_version(checkout)
        modules[name] = {
            "commit": head,
            "version": tag,
            "distribution_version": distribution_version,
        }
    if require_release_tags:
        offenders = [
            f"{name} (tag {entry['version'] or 'missing'}, distribution version {entry['distribution_version'] or 'missing'})"
            for name, entry in modules.items()
            if entry["version"]
            != (f"v{entry['distribution_version']}" if entry["distribution_version"] is not None else None)
        ]
        if offenders:
            raise EcosystemManifestError("release tags required for every module; offenders: " + ", ".join(offenders))
    return {"schema_version": 1, "modules": modules}


def read_ecosystem_manifest(path: str | Path) -> dict[str, object]:
    """Read a JSON manifest and report malformed files as typed errors."""

    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EcosystemManifestError(f"cannot read ecosystem manifest {manifest_path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("modules"), dict):
        raise EcosystemManifestError(f"invalid ecosystem manifest schema: {manifest_path}")
    return value


def write_ecosystem_manifest(manifest: Mapping[str, object], output: str | Path) -> None:
    """Write *manifest* as sorted, newline-terminated JSON using an atomic replace."""

    destination = Path(output).expanduser()
    if destination.is_symlink():
        raise EcosystemManifestError(f"refusing symlink manifest destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.staging-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.is_symlink():
            raise EcosystemManifestError(f"refusing symlink manifest destination: {destination}")
        os.replace(temporary, destination)
    except OSError as exc:
        raise EcosystemManifestError(f"cannot write ecosystem manifest {destination}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def verify_ecosystem_manifest(
    submodules_dir: str | Path,
    manifest_path: str | Path,
    *,
    require_release_tags: bool = False,
) -> None:
    """Verify a committed manifest against the current checkout state."""

    expected = build_ecosystem_manifest(submodules_dir, require_release_tags=require_release_tags)
    actual = read_ecosystem_manifest(manifest_path)
    if actual != expected:
        raise EcosystemManifestError(f"ecosystem manifest drift detected: {manifest_path}")
