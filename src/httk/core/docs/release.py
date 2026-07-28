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

"""Release-tag checks, lock validation, and deterministic documentation URLs.

When ``docs/versioning.toml`` is present, release checks assume each internal
repository's Sphinx project name equals its configured documentation slug and
validate the corresponding committed ``docs/_inventories/<slug>.inv`` header.
"""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, VersioningConfig, load_versioning_config
from .inventories import InventoryError, read_inventory_header
from .lockfile import LockError, check_lock, read_lock_pins
from .semver import Version, VersionError, parse_tag, parse_version

__all__ = ["ReleaseCheck", "ReleaseError", "check_release", "dependency_doc_targets"]


class ReleaseError(RuntimeError):
    """Raised when a release tag, project version, or documentation lock is invalid."""


@dataclass(frozen=True)
class ReleaseCheck:
    """Summary of a successful release preflight."""

    tag: str
    version: Version
    lock_path: Path


def check_release(project_dir: str | Path, tag: str) -> ReleaseCheck:
    """Validate a release tag against ``pyproject.toml`` and its docs lock."""

    project = Path(project_dir).resolve()
    try:
        version = parse_tag(tag)
    except VersionError as exc:
        raise ReleaseError(str(exc)) from exc
    pyproject = project / "pyproject.toml"
    try:
        with pyproject.open("rb") as stream:
            metadata = tomllib.load(stream).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseError(f"cannot read {pyproject}: {exc}") from exc
    if not isinstance(metadata, dict) or not isinstance(metadata.get("version"), str):
        raise ReleaseError(f"{pyproject}: project.version is missing")
    try:
        project_version = parse_version(metadata["version"])
    except VersionError as exc:
        raise ReleaseError(f"{pyproject}: project.version is invalid: {exc}") from exc
    if project_version != version:
        raise ReleaseError(f"tag {tag!r} does not match project.version {metadata['version']!r}")
    lock_path = project / "docs" / "requirements.lock"
    if not lock_path.is_file():
        raise ReleaseError(f"documentation lock is missing: {lock_path}")
    try:
        check_lock(project, lock_path)
    except LockError as exc:
        raise ReleaseError(str(exc)) from exc
    versioning_path = project / "docs" / "versioning.toml"
    if versioning_path.is_file():
        try:
            config = load_versioning_config(versioning_path)
            pins = read_lock_pins(lock_path)
            _check_dependency_inventories(project, config, pins)
        except ConfigError as exc:
            raise ReleaseError(str(exc)) from exc
    return ReleaseCheck(tag, version, lock_path)


def _check_dependency_inventories(
    project: Path,
    config: VersioningConfig,
    pins: Mapping[str, str],
) -> None:
    for dependency in config.internal_dependencies:
        key = _normalized(dependency.distribution)
        if key not in pins:
            raise ReleaseError(
                f"dependency {dependency.distribution!r} is missing from lock file docs/requirements.lock"
            )
        try:
            expected_version = parse_version(pins[key])
        except VersionError as exc:
            raise ReleaseError(f"locked version for {dependency.distribution!r} is invalid: {pins[key]!r}") from exc
        inventory_path = project / "docs" / "_inventories" / f"{dependency.slug}.inv"
        if not inventory_path.is_file():
            raise ReleaseError(
                f"inventory file {inventory_path} is missing; expected project {dependency.slug!r} "
                f"and version {expected_version}"
            )
        try:
            found_project, found_version = read_inventory_header(inventory_path)
        except InventoryError as exc:
            raise ReleaseError(f"inventory file {inventory_path}: {exc}") from exc
        if found_project != dependency.slug or found_version != str(expected_version):
            raise ReleaseError(
                f"inventory file {inventory_path}: expected project {dependency.slug!r} and version "
                f"{expected_version}, found project {found_project!r} and version {found_version!r}"
            )


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_doc_targets(
    config: VersioningConfig,
    pins: Mapping[str, str],
    base_url: str,
    channel: str,
) -> dict[str, str]:
    """Derive exact release or ``dev/main`` inventory URLs for internal dependencies."""

    if channel not in {"release", "dev"}:
        raise ValueError(f"unknown documentation channel: {channel!r}")
    base = base_url.rstrip("/")
    targets: dict[str, str] = {}
    for dependency in config.internal_dependencies:
        if channel == "dev":
            targets[dependency.distribution] = f"{base}/{dependency.slug}/dev/main/"
            continue
        key = _normalized(dependency.distribution)
        if key not in pins:
            raise ReleaseError(
                f"dependency {dependency.distribution!r} is missing from lock file docs/requirements.lock"
            )
        try:
            version = parse_version(pins[key])
        except VersionError as exc:
            raise ValueError(f"locked version for {dependency.distribution!r} is invalid: {pins[key]!r}") from exc
        targets[dependency.distribution] = f"{base}/{dependency.slug}/{version.tag}/"
    return targets
