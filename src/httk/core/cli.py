"""Extensible root command-line interface for httk."""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .register import cli_command, known_cli_commands


@dataclass(frozen=True)
class CLIContext:
    """Invocation context passed to a registered top-level command."""

    program: str
    cwd: Path


def _version() -> str:
    try:
        return version("httk-core")
    except PackageNotFoundError:
        # Source-tree execution has no requirement to install package metadata.
        return "unknown"


def _root_help(program: str) -> str:
    lines = [
        f"usage: {program} [-C DIR] [--help] [--version] COMMAND [ARG ...]",
        "",
        "The high-throughput toolkit command line.",
        "",
        "options:",
        "  -C DIR       run as if httk was started in DIR",
        "  -h, --help   show this help message",
        "  --version    show the httk-core version",
        "",
        "commands:",
        "  help         show root help or help for one command",
    ]
    for name in known_cli_commands():
        command = cli_command(name)
        assert command is not None
        lines.append(f"  {name:<12s} {command.summary}")
    return "\n".join(lines)


def _error(program: str, message: str) -> int:
    print(f"{program}: {message}", file=sys.stderr)
    print(f"Try '{program} --help' for more information.", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the :command:`httk` executable."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    program = Path(sys.argv[0]).name if argv is None else "httk"
    directory: str | None = None
    position = 0
    while position < len(arguments):
        argument = arguments[position]
        if argument == "-C":
            if position + 1 >= len(arguments):
                return _error(program, "option -C requires a directory")
            directory = arguments[position + 1]
            del arguments[position : position + 2]
            continue
        if argument.startswith("-C") and argument != "-C":
            directory = argument[2:]
            del arguments[position]
            continue
        break

    if directory is not None:
        try:
            os.chdir(directory)
        except OSError as exc:
            return _error(program, f"cannot change directory to {directory!r}: {exc}")

    context = CLIContext(program=program, cwd=Path.cwd())
    if not arguments or arguments[0] in {"-h", "--help"}:
        print(_root_help(program))
        return 0
    if arguments[0] == "--version":
        print(f"{program} {_version()}")
        return 0
    if arguments[0] == "help":
        if len(arguments) == 1:
            print(_root_help(program))
            return 0
        if len(arguments) != 2:
            return _error(program, "help accepts at most one command")
        command = cli_command(arguments[1])
        if command is None:
            return _error(program, f"unknown command: {arguments[1]}")
        return int(command.resolve()(["--help"], context))

    name = arguments.pop(0)
    command = cli_command(name)
    if command is None:
        return _error(program, f"unknown command: {name}")
    try:
        return int(command.resolve()(arguments, context))
    except KeyboardInterrupt:
        print(f"{program}: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
