#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Portable documentation lock files and injectable ``uv pip compile`` tooling.

The lock keeps four contract headers: schema, a canonical-input SHA-256 hash,
Python 3.12, and Linux.  The resolver's comment noise is discarded; only
``name==version`` pins are retained after the headers.  Its pins cover runtime,
documentation, and build-backend requirements so a clean Python 3.12
environment can install the lock before using ``--no-build-isolation``.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

__all__ = [
    "LockError",
    "check_lock",
    "compute_input_hash",
    "filter_lock_pins",
    "generate_lock",
    "internal_pins",
    "read_lock_pins",
]


class LockError(RuntimeError):
    """Raised when a documentation lock is absent, stale, or cannot be made."""


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _load_pyproject(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            metadata = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LockError(f"cannot read project metadata {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise LockError(f"{path}: project metadata must be a table")
    return metadata


def _build_requirements(metadata: dict[str, object], path: Path) -> list[str]:
    build_system = metadata.get("build-system", {})
    if not isinstance(build_system, dict):
        raise LockError(f"{path}: build-system must be a table")
    requirements = build_system.get("requires", [])
    if not isinstance(requirements, list) or any(not isinstance(item, str) for item in requirements):
        raise LockError(f"{path}: build-system.requires must be an array of strings")
    return sorted(requirements)


def compute_input_hash(pyproject_path: str | Path) -> str:
    """Hash the documentation dependency inputs, independent of TOML formatting."""

    path = Path(pyproject_path)
    metadata = _load_pyproject(path)
    project = metadata.get("project", {})
    if not isinstance(project, dict):
        raise LockError(f"{path}: project must be a table")
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        raise LockError(f"{path}: project.optional-dependencies must be a table")
    dependencies = project.get("dependencies", [])
    docs = optional.get("docs", [])
    if (
        not isinstance(dependencies, list)
        or not isinstance(docs, list)
        or any(not isinstance(item, str) for item in dependencies)
        or any(not isinstance(item, str) for item in docs)
    ):
        raise LockError(f"{path}: dependency lists must be arrays")
    value = {
        "requires-python": project.get("requires-python"),
        "dependencies": sorted(dependencies),
        "docs": sorted(docs),
        "build-system": _build_requirements(metadata, path),
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


_PIN_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s#]+)$")


def _parse_pins(lines: Iterable[str], path: Path, *, allow_comments: bool) -> list[str]:
    pin_lines: list[str] = []
    names: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") and allow_comments:
            continue
        match = _PIN_PATTERN.fullmatch(stripped)
        if match is None:
            raise LockError(f"unrecognized lock line in {path}: {stripped!r}")
        name = _normalize_name(match.group(1))
        if name in names:
            raise LockError(f"duplicate lock pin {match.group(1)!r} in {path}")
        names.add(name)
        pin_lines.append(stripped)
    if not pin_lines:
        raise LockError(f"lock contains no pins: {path}")
    return sorted(pin_lines, key=lambda line: _normalize_name(line.split("==", 1)[0]))


def generate_lock(
    project_dir: str | Path,
    output_path: str | Path,
    *,
    command_prefix: Sequence[str] | None = None,
) -> None:
    """Generate a lock by invoking ``uv pip compile`` or an injected command."""

    project = Path(project_dir).resolve()
    pyproject = project / "pyproject.toml"
    input_hash = compute_input_hash(pyproject)
    build_requirements = _build_requirements(_load_pyproject(pyproject), pyproject)
    output = Path(output_path)
    if not output.is_absolute():
        output = project / output
    if output.is_symlink():
        raise LockError(f"refusing symlink lock destination: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.staging-", suffix=".txt", dir=output.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    build_input_path: Path | None = None
    try:
        if build_requirements:
            build_descriptor, build_input_name = tempfile.mkstemp(
                prefix=".httk-docs-build-input-", suffix=".txt", dir=project
            )
            build_input_path = Path(build_input_name)
            with os.fdopen(build_descriptor, "w", encoding="utf-8") as stream:
                stream.write("\n".join(build_requirements) + "\n")
        command = list(command_prefix) if command_prefix is not None else ["uv"]
        inputs = ["pyproject.toml"]
        if build_input_path is not None:
            inputs.append(str(build_input_path))
        command.extend(
            [
                "pip",
                "compile",
                *inputs,
                "--extra",
                "docs",
                "--python-version",
                "3.12",
                "--python-platform",
                "linux",
                "--no-header",
                "-o",
                str(temporary_path),
            ]
        )
        result = subprocess.run(command, cwd=project, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise LockError(f"uv pip compile failed ({result.returncode}): {detail}")
        pins = _parse_pins(temporary_path.read_text(encoding="utf-8").splitlines(), temporary_path, allow_comments=True)
        headers = [
            "# httk-docs-lock-schema: 1",
            f"# input-hash: sha256:{input_hash}",
            "# python: 3.12",
            "# platform: linux",
        ]
        temporary_path.write_text("\n".join(headers + pins) + "\n", encoding="utf-8")
        if output.is_symlink():
            raise LockError(f"refusing symlink lock destination: {output}")
        os.replace(temporary_path, output)
    except OSError as exc:
        raise LockError(f"cannot generate lock {output}: {exc}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)
        if build_input_path is not None:
            build_input_path.unlink(missing_ok=True)


def _read_hash_header(lock_path: Path) -> str:
    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise LockError(f"cannot read lock {lock_path}: {exc}") from exc
    expected_headers = [
        "# httk-docs-lock-schema: 1",
        None,
        "# python: 3.12",
        "# platform: linux",
    ]
    if len(lines) < 4 or lines[0] != expected_headers[0]:
        raise LockError(f"lock schema header missing in {lock_path}")
    header = lines[1] if len(lines) > 1 else None
    if header is None or not re.fullmatch(r"# input-hash: sha256:[0-9a-f]{64}", header):
        raise LockError(f"input-hash header missing or invalid in {lock_path}")
    if lines[2] != expected_headers[2]:
        raise LockError(f"python header invalid in {lock_path}; expected # python: 3.12")
    if lines[3] != expected_headers[3]:
        raise LockError(f"platform header invalid in {lock_path}; expected # platform: linux")
    return header.split("sha256:", 1)[1]


def check_lock(project_dir: str | Path, lock_path: str | Path) -> None:
    """Raise :class:`LockError` if a lock is missing or stale for *project_dir*."""

    project = Path(project_dir).resolve()
    path = Path(lock_path)
    if not path.is_absolute():
        path = project / path
    if not path.is_file():
        raise LockError(f"lock file missing: {path}; regenerate with make docs-lock")
    recorded = _read_hash_header(path)
    actual = compute_input_hash(project / "pyproject.toml")
    if recorded != actual:
        raise LockError(f"input-hash mismatch in {path}; regenerate with make docs-lock")
    _parse_pins(path.read_text(encoding="utf-8").splitlines()[4:], path, allow_comments=True)


def read_lock_pins(lock_path: str | Path) -> dict[str, str]:
    """Read normalized distribution names and versions from a lock file."""

    pins: dict[str, str] = {}
    for line in Path(lock_path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "==" not in stripped:
            continue
        name, version = stripped.split("==", 1)
        pins[_normalize_name(name.strip())] = version.strip()
    return pins


def filter_lock_pins(pins: Mapping[str, str], *, drop: Iterable[str]) -> dict[str, str]:
    """Return pins excluding all ``httk-*`` names and the explicitly dropped names."""

    dropped = {_normalize_name(name) for name in drop}
    normalized = {_normalize_name(name): version for name, version in pins.items()}
    return {
        name: version for name, version in normalized.items() if not name.startswith("httk-") and name not in dropped
    }


def internal_pins(pins: Mapping[str, str]) -> dict[str, str]:
    """Return the normalized subset of pins belonging to internal httk distributions."""

    normalized = {_normalize_name(name): version for name, version in pins.items()}
    return {name: version for name, version in normalized.items() if name.startswith("httk-")}
