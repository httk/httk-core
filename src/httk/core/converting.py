"""The core-owned ``httk convert`` command.

``httk convert`` loads a file with :func:`httk.core.load` and writes the result
with :func:`httk.core.save`, so any loadable file becomes any saveable format
when the matching capability modules (for example *httk-atomistic*)
are installed.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from httk.core.cli import CLIContext
from httk.core.loading import load
from httk.core.saving import save

#: Operator-facing failures (unknown format, missing file, bad payload) are
#: reported as ``PROGRAM: message`` and exit ``2``; anything else propagates.
_ERRORS = (OSError, ValueError)


def _build_parser(program: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program,
        description="Convert a loadable file into a saveable format",
    )
    parser.add_argument("input", metavar="INPUT", help="the file to load")
    parser.add_argument("output", metavar="OUTPUT", help="the destination to save")
    parser.add_argument(
        "--format",
        metavar="FORMAT",
        help="writer format for an ambiguous OUTPUT (forwarded to save)",
    )
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level convert command.

    :param argv: Arguments following the convert command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = _build_parser(f"{context.program} convert")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    input_path = context.cwd / Path(arguments.input)
    output_path = context.cwd / Path(arguments.output)
    try:
        save(load(str(input_path)), output_path, format=arguments.format)
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(command(sys.argv[1:], CLIContext("httk", Path.cwd())))
