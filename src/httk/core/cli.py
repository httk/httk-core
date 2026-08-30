"""Extensible root command-line interface for httk."""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .register.cli import cli_command, known_cli_commands


@dataclass(frozen=True)
class CLIContext:
    """Carry invocation context to a registered top-level command.

    :param program: Program name used in command output and help.
    :param cwd: Working directory selected for the command invocation.
    """

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
        "  help         show help for the root, a command, or a subcommand",
    ]
    for name in known_cli_commands():
        command = cli_command(name)
        assert command is not None
        lines.append(f"  {name:<12s} {command.summary}")
    return "\n".join(lines)


def _rewrite_help(arguments: list[str]) -> list[str]:
    """Turn a bare ``help`` in the leading subcommand chain into ``--help``.

    Only tokens before the first option-like token (starting with ``-``) are
    considered; the first ``help`` there is replaced with ``--help`` and the
    tokens after it are dropped, so ``workflow runner help`` becomes
    ``workflow runner --help``. Tokens after an option are never rewritten,
    which keeps ``help`` usable as an option value or a file name.

    :param arguments: Subcommand chain to rewrite.
    :return: Arguments with the first leading ``help`` turned into ``--help``.
    """

    for index, argument in enumerate(arguments):
        if argument.startswith("-"):
            break
        if argument == "help":
            return arguments[:index] + ["--help"]
    return arguments


def _error(program: str, message: str) -> int:
    print(f"{program}: {message}", file=sys.stderr)
    print(f"Try '{program} --help' for more information.", file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the httk executable.

    The optional -C prefix changes the process working directory before
    resolving the command, and the returned value is the command's exit code.

    :param argv: Command-line arguments without the executable name, or None to use sys.argv.
    :return: Exit status for the requested command.
    """

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
        command = cli_command(arguments[1])
        if command is None:
            return _error(program, f"unknown command: {arguments[1]}")
        rest = _rewrite_help(arguments[2:])
        if rest[-1:] != ["--help"]:
            rest.append("--help")
        return int(command.resolve()(rest, context))

    name = arguments.pop(0)
    command = cli_command(name)
    if command is None:
        return _error(program, f"unknown command: {name}")
    arguments = _rewrite_help(arguments)
    try:
        return int(command.resolve()(arguments, context))
    except KeyboardInterrupt:
        print(f"{program}: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
