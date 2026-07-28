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

"""The ``httk docs`` command-line adapter over the documentation library."""

import argparse
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from httk.core.cli_context import CLIContext

from .ecosystem import (
    EcosystemManifestError,
    build_ecosystem_manifest,
    verify_ecosystem_manifest,
    write_ecosystem_manifest,
)
from .gitsite import GitSiteError, commit_site
from .inventories import InventoryError, fetch_inventory
from .lockfile import (
    LockError,
    check_lock,
    filter_lock_pins,
    generate_lock,
    read_lock_pins,
)
from .release import ReleaseError, check_release
from .semver import Version, VersionError, parse_tag, parse_version
from .sitetree import ImmutabilityError, compose_site

__all__ = ["build_parser", "command"]

_ERRORS = (
    OSError,
    ValueError,
    RuntimeError,
    LockError,
    InventoryError,
    ReleaseError,
    ImmutabilityError,
    GitSiteError,
    EcosystemManifestError,
)


def build_parser(program: str, project_dir: Path) -> argparse.ArgumentParser:
    """Build the ``httk docs`` parser with a project-directory default."""

    parser = argparse.ArgumentParser(prog=program, description="Maintain versioned httk documentation sites")
    parser.set_defaults(handler=None, help_parser=parser)
    subparsers = parser.add_subparsers(dest="subcommand", metavar="COMMAND")

    lock = subparsers.add_parser("lock", help="generate the documentation lock")
    lock.set_defaults(handler=_handle_lock, help_parser=lock)
    _add_project_dir(lock, project_dir)
    lock.add_argument("--out", type=Path, help="lock output path (default: PROJECT/docs/requirements.lock)")

    lock_check = subparsers.add_parser("lock-check", help="check the documentation lock")
    lock_check.set_defaults(handler=_handle_lock_check, help_parser=lock_check)
    _add_project_dir(lock_check, project_dir)
    lock_check.add_argument("--lock", type=Path, help="lock path (default: PROJECT/docs/requirements.lock)")

    compose = subparsers.add_parser("compose", help="compose a docs-site tree")
    compose.set_defaults(handler=_handle_compose, help_parser=compose)
    compose.add_argument("--site", required=True, type=Path)
    compose.add_argument("--build", required=True, type=Path)
    targets = compose.add_mutually_exclusive_group(required=True)
    targets.add_argument("--release", type=str)
    targets.add_argument("--dev", action="store_true")
    targets.add_argument("--repair", metavar="VERSION", help="replace an existing release after approved repair")
    compose.add_argument("--slug", required=True)
    compose.add_argument("--url", required=True)
    compose.add_argument("--source-commit")

    release = subparsers.add_parser("check-release", help="check a release tag and docs lock")
    release.set_defaults(handler=_handle_release, help_parser=release)
    _add_project_dir(release, project_dir)
    release.add_argument("--tag", required=True)

    filtered = subparsers.add_parser("filter-lock", help="remove internal pins from a lock")
    filtered.set_defaults(handler=_handle_filter, help_parser=filtered)
    filtered.add_argument("--lock", required=True, type=Path)
    filtered.add_argument("--out", required=True, type=Path)
    filtered.add_argument("--self-distribution", required=True)

    inventory = subparsers.add_parser("fetch-inventory", help="fetch and validate an intersphinx inventory")
    inventory.set_defaults(handler=_handle_inventory, help_parser=inventory)
    inventory.add_argument("url")
    inventory.add_argument("dest", type=Path)
    inventory.add_argument("--expect-project")
    inventory.add_argument("--expect-version")

    refresh = subparsers.add_parser("refresh-inventories", help="refresh committed internal dependency inventories")
    refresh.set_defaults(handler=_handle_refresh_inventories, help_parser=refresh)
    _add_project_dir(refresh, project_dir)
    refresh.add_argument(
        "--base-url", default=None, help="documentation site base URL (default: HTTK_DOCS_BASE_URL or docs.httk.org)"
    )
    refresh.add_argument("--channel", required=True, choices=("release", "dev"))

    commit = subparsers.add_parser("commit-site", help="commit a generated site as one orphan branch commit")
    commit.set_defaults(handler=_handle_commit_site, help_parser=commit)
    commit.add_argument("--site", required=True, type=Path)
    commit.add_argument("--repo", type=Path, help="repository directory (default: repository containing --site)")
    commit.add_argument("--branch", required=True)
    commit.add_argument("--message", required=True)

    ecosystem = subparsers.add_parser("ecosystem-manifest", help="write or verify module checkout metadata")
    ecosystem.set_defaults(handler=_handle_ecosystem_manifest, help_parser=ecosystem)
    ecosystem.add_argument("--submodules-dir", required=True, type=Path)
    ecosystem.add_argument("--out", type=Path, help="manifest output path")
    ecosystem.add_argument("--verify", type=Path, help="verify an existing manifest instead of writing")
    ecosystem.add_argument("--require-release-tags", action="store_true")
    return parser


def _add_project_dir(parser: argparse.ArgumentParser, default: Path) -> None:
    parser.add_argument(
        "--project-dir", type=lambda value: Path(value).expanduser().resolve(), default=default.resolve()
    )


def _lock_path(arguments: argparse.Namespace) -> Path:
    return arguments.lock or arguments.project_dir / "docs" / "requirements.lock"


def _handle_lock(arguments: argparse.Namespace, _context: CLIContext) -> int:
    output = arguments.out or arguments.project_dir / "docs" / "requirements.lock"
    generate_lock(arguments.project_dir, output)
    print(f"generated documentation lock: {output}")
    return 0


def _handle_lock_check(arguments: argparse.Namespace, _context: CLIContext) -> int:
    path = _lock_path(arguments)
    check_lock(arguments.project_dir, path)
    print(f"documentation lock is current: {path}")
    return 0


def _handle_compose(arguments: argparse.Namespace, _context: CLIContext) -> int:
    if arguments.dev:
        target: Literal["dev"] | Version = "dev"
        composed = "dev:main"
        repair = False
    else:
        target = _parse_release_argument(arguments.release or arguments.repair)
        composed = target.tag
        repair = arguments.repair is not None
    result = compose_site(
        arguments.site,
        arguments.build,
        slug=arguments.slug,
        site_url=arguments.url,
        source_commit=arguments.source_commit,
        target=target,
        repair=repair,
    )
    print(f"composed {composed}; default: {result.default_target}; versions: {', '.join(result.versions) or '(none)'}")
    return 0


def _parse_release_argument(text: str) -> Version:
    """Parse a compose release as either ``vX.Y.Z`` or ``X.Y.Z``."""

    try:
        return parse_tag(text)
    except VersionError:
        try:
            return parse_version(text)
        except VersionError as exc:
            raise VersionError(f"invalid release {text!r}; expected vX.Y.Z or X.Y.Z") from exc


def _handle_release(arguments: argparse.Namespace, _context: CLIContext) -> int:
    result = check_release(arguments.project_dir, arguments.tag)
    print(f"release check passed: {result.tag}")
    return 0


def _handle_filter(arguments: argparse.Namespace, _context: CLIContext) -> int:
    pins = read_lock_pins(arguments.lock)
    filtered = filter_lock_pins(pins, drop=[arguments.self_distribution])
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        "\n".join(f"{name}=={version}" for name, version in sorted(filtered.items())) + "\n", encoding="utf-8"
    )
    print(f"wrote filtered lock: {arguments.out}")
    return 0


def _handle_inventory(arguments: argparse.Namespace, _context: CLIContext) -> int:
    project, version = fetch_inventory(
        arguments.url,
        arguments.dest,
        expected_project=arguments.expect_project,
        expected_version=arguments.expect_version,
    )
    print(f"fetched inventory: {project} {version}")
    return 0


def _handle_refresh_inventories(arguments: argparse.Namespace, _context: CLIContext) -> int:
    """Refresh all committed inventories declared by versioning.toml."""

    from .config import load_versioning_config

    project = arguments.project_dir
    versioning_path = project / "docs" / "versioning.toml"
    config = load_versioning_config(versioning_path)
    base_url = arguments.base_url or os.environ.get("HTTK_DOCS_BASE_URL", "https://docs.httk.org")
    pins: dict[str, str] = {}
    lock_path = project / "docs" / "requirements.lock"
    if arguments.channel == "release":
        if not lock_path.is_file():
            raise LockError(f"documentation lock is missing: {lock_path}; required for release inventories")
        try:
            pins = read_lock_pins(lock_path)
        except OSError as exc:
            raise LockError(f"cannot read documentation lock {lock_path}: {exc}") from exc

    destination_dir = project / "docs" / "_inventories"
    destination_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".httk-inventories-", dir=destination_dir))
    refreshed: list[tuple[str, Path, Path, str]] = []
    try:
        for dependency in config.internal_dependencies:
            if arguments.channel == "release":
                try:
                    normalized_distribution = re.sub(r"[-_.]+", "-", dependency.distribution).lower()
                    pin = pins[normalized_distribution]
                except KeyError as exc:
                    raise LockError(
                        f"dependency {dependency.distribution!r} is missing from lock file {lock_path}"
                    ) from exc
                url = f"{base_url.rstrip('/')}/{dependency.slug}/v{pin}/objects.inv"
                expected_version = pin
            else:
                url = f"{base_url.rstrip('/')}/{dependency.slug}/dev/main/objects.inv"
                expected_version = "dev:main"
            staged = staging_dir / f"{dependency.slug}.inv"
            destination = destination_dir / f"{dependency.slug}.inv"
            try:
                fetch_inventory(
                    url,
                    staged,
                    expected_project=dependency.slug,
                    expected_version=expected_version,
                )
            except (InventoryError, OSError) as exc:
                raise InventoryError(f"failed to refresh inventory for {dependency.slug!r} from {url}: {exc}") from exc
            refreshed.append((dependency.slug, staged, destination, url))

        for _slug, _staged, destination, _url in refreshed:
            if destination.is_symlink():
                raise InventoryError(f"refusing symlink inventory destination: {destination}")
        for _slug, staged, destination, _url in refreshed:
            os.replace(staged, destination)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    for slug, _staged, _destination, url in refreshed:
        print(f"refreshed {slug} inventory from {url}")
    return 0


def _handle_commit_site(arguments: argparse.Namespace, _context: CLIContext) -> int:
    result = commit_site(
        arguments.site,
        arguments.branch,
        arguments.message,
        repository=arguments.repo,
    )
    print(f"committed {result.branch} as orphan {result.commit} (tree {result.tree})")
    return 0


def _handle_ecosystem_manifest(arguments: argparse.Namespace, _context: CLIContext) -> int:
    if (arguments.out is None) == (arguments.verify is None):
        raise EcosystemManifestError("ecosystem-manifest requires exactly one of --out or --verify")
    if arguments.verify is not None:
        verify_ecosystem_manifest(
            arguments.submodules_dir,
            arguments.verify,
            require_release_tags=arguments.require_release_tags,
        )
        print(f"ecosystem manifest is current: {arguments.verify}")
    else:
        manifest = build_ecosystem_manifest(
            arguments.submodules_dir,
            require_release_tags=arguments.require_release_tags,
        )
        write_ecosystem_manifest(manifest, arguments.out)
        print(f"wrote ecosystem manifest: {arguments.out}")
    return 0


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level ``docs`` command."""

    parser = build_parser(f"{context.program} docs", context.cwd)
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    handler = getattr(arguments, "handler", None)
    if handler is None:
        getattr(arguments, "help_parser", parser).print_help()
        return 0
    try:
        return handler(arguments, context)
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 1
