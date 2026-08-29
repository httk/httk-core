"""The core-owned ``httk system`` command for managing per-user state."""

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from httk.core.cli import CLIContext
from httk.core.userdirs import config_home, data_home


def _build_parser(program: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=program, description="Manage per-user httk state")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    reset_parser = subparsers.add_parser("reset", help="remove per-user httk state")
    reset_parser.add_argument("-f", "--force", action="store_true", help="do not prompt for confirmation")
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level system command.

    :param argv: Arguments following the system command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = _build_parser(f"{context.program} system")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    targets = [config_home(), data_home()]
    home = Path.home().resolve()
    for target in targets:
        if target.parent == target or target == home:
            print(f"{parser.prog}: refusing to remove {target}", file=sys.stderr)
            return 2

    print("WARNING! This will remove all httk per-user configuration and data:")
    for target in targets:
        print(f"  - {target}")

    if not arguments.force:
        if not sys.stdin.isatty():
            print(
                f"{parser.prog}: refusing to reset without --force when stdin is not a terminal",
                file=sys.stderr,
            )
            return 2
        try:
            answer = input("Are you sure you want to continue? [y/N] ")
        except EOFError:
            return 1
        if answer.strip().lower() not in {"y", "yes"}:
            return 1

    for target in targets:
        try:
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                continue
        except OSError as exc:
            print(f"{parser.prog}: cannot remove {target}: {exc}", file=sys.stderr)
            return 2
        print(f"removed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(command(sys.argv[1:], CLIContext("httk", Path.cwd())))
