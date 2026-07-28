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

"""JSON manifests used by the documentation site's root and selector."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .semver import Version

__all__ = [
    "build_page_manifest",
    "build_version_manifest",
    "read_version_manifest",
    "write_page_manifest",
    "write_version_manifest",
]


def build_version_manifest(
    slug: str,
    url: str,
    source_commit: str | None,
    release_versions: list[Version] | tuple[Version, ...],
    has_dev: bool,
) -> dict[str, Any]:
    """Build a root manifest with releases newest-first and optional dev last."""

    releases = sorted(release_versions, reverse=True)
    versions: list[dict[str, str]] = [
        {"name": version.tag, "path": f"{version.tag}/", "channel": "release"} for version in releases
    ]
    if has_dev:
        versions.append({"name": "dev:main", "path": "dev/main/", "channel": "dev"})
    if releases:
        default = {"name": releases[0].tag, "path": f"{releases[0].tag}/", "channel": "release"}
    else:
        default = {"name": "dev:main", "path": "dev/main/", "channel": "dev"}
    return {
        "schema_version": 1,
        "project": slug,
        "url": url,
        "source_commit": source_commit,
        "default": default,
        "versions": versions,
    }


def write_version_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    """Write one JSON version manifest using stable, human-readable formatting."""

    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(manifest_path, json.dumps(manifest, indent=2, sort_keys=False) + "\n")


def read_version_manifest(path: str | Path) -> dict[str, Any]:
    """Read a JSON version manifest from *path*."""

    with Path(path).open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"version manifest is not an object: {path}")
    return value


def build_page_manifest(version_name: str, html_dir: str | Path) -> dict[str, Any]:
    """List every HTML page below *html_dir* as sorted POSIX paths."""

    root = Path(html_dir)
    pages = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.html") if path.is_file())
    return {"schema_version": 1, "version": version_name, "pages": pages}


def write_page_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    """Write one per-version page manifest."""

    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(manifest_path, json.dumps(manifest, indent=2, sort_keys=False) + "\n")


def _write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.staging-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
