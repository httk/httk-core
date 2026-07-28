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
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from httk.core.cli_context import CLIContext

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

_ERRORS = (OSError, ValueError, RuntimeError, LockError, InventoryError, ReleaseError, ImmutabilityError)


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
    else:
        target = _parse_release_argument(arguments.release)
        composed = target.tag
    result = compose_site(
        arguments.site,
        arguments.build,
        slug=arguments.slug,
        site_url=arguments.url,
        source_commit=arguments.source_commit,
        target=target,
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
