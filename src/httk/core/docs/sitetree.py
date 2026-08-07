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

"""Compose immutable release and replaceable development documentation trees."""

import errno
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .manifests import build_page_manifest, build_version_manifest, write_page_manifest
from .redirect import root_redirect_html
from .semver import Version, is_release_dir_name, parse_tag

__all__ = ["ComposeError", "ComposeResult", "ImmutabilityError", "compose_site"]

_LOGGER = logging.getLogger(__name__)


class ComposeError(RuntimeError):
    """Raised when a documentation tree contains unsafe or unsupported entries."""


class ImmutabilityError(RuntimeError):
    """Raised when a rebuild differs from an already published release tree."""


@dataclass(frozen=True)
class ComposeResult:
    """Summarize one site composition operation.

    :param changed: Whether any generated site file changed.
    :param unchanged: Whether the requested target tree already matched.
    :param default_target: Manifest name selected as the site's default.
    :param versions: All published version labels, including development channels.
    """

    changed: bool
    unchanged: bool
    default_target: str
    versions: tuple[str, ...]


def _validate_tree(root: Path) -> None:
    """Reject symlinks and non-regular nodes without following them."""

    if root.is_symlink():
        raise ComposeError(f"symlink is not allowed in documentation tree: {root}")
    if not root.exists():
        raise ComposeError(f"documentation tree does not exist: {root}")
    if not root.is_dir():
        raise ComposeError(f"documentation tree is not a directory: {root}")
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            raise ComposeError(f"cannot inspect documentation tree {current}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                raise ComposeError(f"symlink is not allowed in documentation tree: {path}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif not entry.is_file(follow_symlinks=False):
                raise ComposeError(f"non-regular file is not allowed in documentation tree: {path}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree(root: Path) -> dict[str, str]:
    _validate_tree(root)
    files: dict[str, str] = {}
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in os.scandir(current):
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            else:
                files[path.relative_to(root).as_posix()] = _file_hash(path)
    return files


def _copy_tree(source: Path, destination: Path) -> None:
    _validate_tree(source)

    def copy(current: Path, target_root: Path) -> None:
        target_root.mkdir(parents=True, exist_ok=True)
        for entry in os.scandir(current):
            item = Path(entry.path)
            target = target_root / entry.name
            if entry.is_dir(follow_symlinks=False):
                copy(item, target)
            else:
                shutil.copy2(item, target)

    copy(source, destination)


def _prepare_version(source: Path, destination: Path, version_name: str) -> None:
    _copy_tree(source, destination)
    write_page_manifest(destination / "pages.json", build_page_manifest(version_name, destination))


def _differing_paths(left: dict[str, str], right: dict[str, str]) -> list[str]:
    return sorted(path for path in set(left) | set(right) if left.get(path) != right.get(path))


def _write_if_changed(path: Path, content: str) -> bool:
    if path.is_file() and not path.is_symlink() and path.read_text(encoding="utf-8") == content:
        return False
    _write_atomic(path, content)
    return True


def _write_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.staging-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _remove_staging(root: Path) -> None:
    for path in root.iterdir():
        if not path.name.startswith(".staging-"):
            continue
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)


def _remove_old_dev(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def _recover_swap(root: Path, destination: Path, prefix: str) -> None:
    """Recover an interrupted directory swap before starting a new composition."""

    if destination == root / "dev" / "main":
        dev_parent = root / "dev"
        if dev_parent.is_symlink():
            raise ComposeError(f"symlink is not allowed for dev directory: {dev_parent}")
        if dev_parent.exists() and not dev_parent.is_dir():
            raise ComposeError(f"dev path is not a directory: {dev_parent}")
    old_paths = sorted(path for path in root.iterdir() if path.name.startswith(prefix))
    if not old_paths:
        return
    if destination.exists() or destination.is_symlink():
        for path in old_paths:
            _remove_old_dev(path)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.rename(old_paths[-1], destination)
    for path in old_paths[:-1]:
        _remove_old_dev(path)


def _reconcile_latest(root: Path, release_versions: list[Version]) -> bool:
    """Refresh the maintained latest duplicate to match the newest release."""

    latest = root / "latest"
    if latest.is_symlink():
        raise ComposeError(f"symlink is not allowed for latest directory: {latest}")
    if latest.exists() and not latest.is_dir():
        raise ComposeError(f"latest path is not a directory: {latest}")
    if not release_versions:
        if latest.exists():
            staging = _new_empty_sibling(root, ".staging-latest-")
            os.rename(latest, staging)
            _remove_old_dev(staging)
            return True
        return False

    source = root / release_versions[0].tag
    if latest.exists() and _tree(latest) == _tree(source):
        return False
    staging = _new_staging(root, "latest")
    old = None
    try:
        _copy_tree(source, staging)
        if latest.exists():
            old = _new_empty_sibling(root, ".old-latest-")
            os.rename(latest, old)
        os.rename(staging, latest)
    except BaseException:
        if old is not None and old.exists() and not latest.exists():
            os.rename(old, latest)
        if staging.exists():
            _remove_old_dev(staging)
        raise
    if old is not None and old.exists():
        _remove_old_dev(old)
    return True


def _new_staging(root: Path, version_name: str) -> Path:
    safe_name = version_name.replace(":", "-")
    return Path(tempfile.mkdtemp(prefix=f".staging-{safe_name}-", dir=root))


def _new_empty_sibling(root: Path, prefix: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=root))
    path.rmdir()
    return path


def _release_versions(root: Path) -> list[Version]:
    versions: list[Version] = []
    for path in root.iterdir():
        if path.name.startswith("v") and is_release_dir_name(path.name):
            if path.is_symlink():
                raise ComposeError(f"symlink is not allowed for release directory: {path}")
            if not path.is_dir():
                raise ComposeError(f"release path is not a directory: {path}")
            versions.append(parse_tag(path.name))
    return sorted(versions, reverse=True)


def compose_site(
    site_root: Path,
    build_html: Path,
    *,
    slug: str,
    site_url: str,
    source_commit: str | None,
    target: Version | Literal["dev"],
    repair: bool = False,
) -> ComposeResult:
    """Compose a docs-site tree while preserving releases and maintaining latest.

    The root redirect lands on ``latest/`` when a release exists; ``latest/``
    is a replaceable duplicate of the newest release tree.

    ``repair=True`` is reserved for replacing an existing release after an
    approved manual repair. The replacement uses the same rename transaction
    as the development swap and never removes the live release in place.

    :param site_root: Root directory of the composed documentation site.
    :param build_html: Generated HTML tree to publish.
    :param slug: Site slug stored in the version manifest.
    :param site_url: Public site URL stored in the version manifest.
    :param source_commit: Source commit recorded in the version manifest.
    :param target: Release version or the replaceable development target.
    :param repair: Whether to replace an existing release after manual approval.
    :return: Summary of the composition result.
    :raises ComposeError: If the source, destination, or target is unsafe or invalid.
    :raises ImmutabilityError: If an existing release differs from the rebuilt tree.
    """

    root = Path(site_root)
    source = Path(build_html)
    if root.exists() and root.is_symlink():
        raise ComposeError(f"symlink is not allowed for site root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    _remove_staging(root)
    _recover_swap(root, root / "dev" / "main", ".old-dev-main-")
    _recover_swap(root, root / "latest", ".old-latest-")
    _validate_tree(source)
    is_dev = target == "dev"
    if repair and is_dev:
        raise ComposeError("--repair is only valid for a release target, not --dev")
    if repair and not isinstance(target, Version):
        raise ComposeError("--repair requires a release target")
    if is_dev:
        version_name = "dev:main"
    else:
        assert isinstance(target, Version)
        version_name = target.tag
    destination = root / "dev" / "main" if is_dev else root / version_name
    if destination.is_symlink():
        raise ComposeError(f"symlink is not allowed for destination: {destination}")
    existed = destination.exists()
    if existed and not destination.is_dir():
        raise ComposeError(f"destination is not a directory: {destination}")

    staging = _new_staging(root, version_name)
    _prepare_version(source, staging, version_name)
    staged_tree = _tree(staging)
    unchanged = False
    if is_dev:
        old = None
        try:
            if existed:
                old = _new_empty_sibling(root, ".old-dev-main-")
                os.rename(destination, old)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staging, destination)
        except BaseException:
            if old is not None and old.exists() and not destination.exists():
                os.rename(old, destination)
            raise
        if old is not None and old.exists():
            _remove_old_dev(old)
    elif repair:
        if not existed:
            _remove_old_dev(staging)
            raise ComposeError(f"cannot repair nonexistent release {version_name}")
        _LOGGER.warning("repairing immutable documentation release %s", version_name)
        old = _new_empty_sibling(root, f".old-release-{version_name}-")
        try:
            os.rename(destination, old)
            os.rename(staging, destination)
        except BaseException:
            if old.exists() and not destination.exists():
                os.rename(old, destination)
            if staging.exists():
                _remove_old_dev(staging)
            raise
        _remove_old_dev(old)
    elif existed:
        differing = _differing_paths(_tree(destination), staged_tree)
        if differing:
            sample = ", ".join(differing[:6])
            more = " ..." if len(differing) > 6 else ""
            _remove_old_dev(staging)
            raise ImmutabilityError(
                f"release {version_name} differs at {sample}{more}; release directories are immutable; "
                "repairs go through the manual repair workflow"
            )
        unchanged = True
        _remove_old_dev(staging)
    else:
        try:
            os.rename(staging, destination)
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise
            differing = _differing_paths(_tree(destination), _tree(staging))
            if differing:
                sample = ", ".join(differing[:6])
                more = " ..." if len(differing) > 6 else ""
                _remove_old_dev(staging)
                raise ImmutabilityError(
                    f"release {version_name} differs at {sample}{more}; release directories are immutable; "
                    "repairs go through the manual repair workflow"
                )
            unchanged = True
            _remove_old_dev(staging)

    release_versions = _release_versions(root)
    latest_changed = _reconcile_latest(root, release_versions)
    has_dev = (root / "dev" / "main").is_dir()
    manifest = build_version_manifest(slug, site_url, source_commit, release_versions, has_dev)
    manifest_text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    changed = not unchanged
    changed |= latest_changed
    versions_path = root / "versions.json"
    if _write_if_changed(versions_path, manifest_text):
        changed = True
    redirect_target = manifest["default"]["path"]
    redirect_text = root_redirect_html(redirect_target)
    if _write_if_changed(root / "index.html", redirect_text):
        changed = True
    nojekyll = root / ".nojekyll"
    if not nojekyll.exists() or nojekyll.is_symlink():
        _write_atomic(nojekyll, "")
        changed = True
    return ComposeResult(
        changed, unchanged, manifest["default"]["name"], tuple(item["name"] for item in manifest["versions"])
    )
