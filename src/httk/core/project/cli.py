"""The core-owned ``httk project`` command.

``httk project`` owns the anchor: ``init`` creates one (like ``git init``) and
``show`` describes it, and ``import-v1`` migrates a legacy project.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from httk.core.cli import CLIContext

from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    import_v1_project,
    initialize_project,
    key_fingerprint,
    pinned_project_key,
    read_project,
    require_project,
    trusted_project_keys,
)

#: Everything a handler may raise that is an operator's problem rather than a
#: defect. Anything here is reported as ``PROGRAM: message`` and exits ``2``.
_ERRORS = (OSError, ValueError, RuntimeError)

#: The handler contract every project subcommand honors, the same one the root
#: :command:`httk` commands use.
Handler = Callable[[argparse.Namespace, CLIContext], int]


def _key_record(value: str) -> dict[str, object]:
    return {"public_key": value, "fingerprint": key_fingerprint(value)}


def _field(name: str, value: object) -> str:
    """Render one name/value line of a human-readable description."""

    return f"{name:<22}{value}"


def describe_project(
    root: str | Path | None = None,
    *,
    verify: bool = True,
) -> dict[str, object]:
    """Describe one project's anchor."""

    project = require_project(root)
    metadata = read_project(project)
    own = pinned_project_key(metadata)
    trusted = trusted_project_keys(metadata)
    seed = project / PROJECT_DIRECTORY / "keys" / "project.seed"
    description: dict[str, object] = {
        "format": "httk-project-description",
        "format_version": 1,
        "root": str(project),
        "project": {
            "project_id": metadata.get("project_id"),
            "name": metadata.get("name"),
            "description": metadata.get("description"),
            "default_queue": metadata.get("default_queue"),
            "imported_from": metadata.get("imported_from"),
            "manifest_exclusions": metadata.get("manifest_exclusions", []),
        },
        "keys": {
            "pinned": own is not None,
            "public_key": None if own is None else _key_record(own),
            "seed_present": seed.is_file(),
            "trusted_keys": [_key_record(key) for key in trusted],
        },
    }
    return description


def _render(description: dict[str, object]) -> str:
    """Render one anchor description as readable lines."""

    project = description.get("project", {})
    keys = description.get("keys", {})
    assert isinstance(project, dict) and isinstance(keys, dict)
    public = keys.get("public_key") or {}
    assert isinstance(public, dict)
    lines = [
        _field("root", description.get("root")),
        _field("name", project.get("name") or "-"),
        _field("project_id", project.get("project_id") or "-"),
        _field("default_queue", project.get("default_queue") or "-"),
        _field("key_pinned", "yes" if keys.get("pinned") else "no"),
        _field("key_fingerprint", public.get("fingerprint") or "-"),
        _field("trusted_keys", len(keys.get("trusted_keys", []))),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in leaves
# ---------------------------------------------------------------------------


def _handle_init(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Create one project anchor at PATH, refusing an existing project."""

    path = Path(arguments.path or context.cwd).expanduser().resolve()
    if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        raise ValueError(f"{path} is already an httk project")
    metadata = initialize_project(
        path,
        name=arguments.name or path.name,
        description=arguments.description,
    )
    print(f"Initialized httk project {metadata['name']!r} in {path / PROJECT_DIRECTORY}")
    return 0


def _handle_import_v1(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Import a legacy v1 project into a new v2 anchor."""

    path = Path(arguments.path or context.cwd).expanduser().resolve()
    if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        raise ValueError(f"{path} is already an httk project")
    source = Path(arguments.source or path / "ht.project").expanduser().resolve()
    import_v1_project(path, source=source, name=arguments.name)
    print(f"imported {source} -> {path / PROJECT_DIRECTORY}")
    return 0


def _handle_show(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Describe the nearest project: its metadata and keys."""

    description = describe_project(arguments.path or context.cwd, verify=not arguments.no_verify)
    if arguments.json:
        print(json.dumps(description, indent=2, sort_keys=True))
    else:
        print(_render(description))
    return 0


def _build_init(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        help="the directory to make a project (default: the working directory)",
    )
    parser.add_argument("--name", metavar="NAME", help="the project name (default: the directory name)")
    parser.add_argument("--description", metavar="TEXT", default="", help="a one-line description")


def _build_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        help="the project to describe (default: the nearest project of the working directory)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="do not let a section walk the tree, which is much cheaper on a large project",
    )
    parser.add_argument("--json", action="store_true", help="print the description as one JSON document")


def _build_import_v1(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        help="the v1 project to import (default: the working directory)",
    )
    parser.add_argument("--source", metavar="DIR", help="the v1 project directory (default: PATH/ht.project)")
    parser.add_argument("--name", metavar="NAME", help="the imported project name")


# ---------------------------------------------------------------------------
# Assembly and dispatch
# ---------------------------------------------------------------------------


def _add_leaf(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
    name: str,
    *,
    summary: str,
    handler: Handler,
    build: Callable[[argparse.ArgumentParser], None],
) -> None:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    parser.set_defaults(handler=handler, help_parser=parser)
    build(parser)


def build_parser(program: str) -> argparse.ArgumentParser:
    """Build the core-owned ``httk project`` command tree."""

    parser = argparse.ArgumentParser(prog=program, description="Create and inspect httk projects")
    parser.set_defaults(handler=None, help_parser=parser)
    subparsers = parser.add_subparsers(metavar="COMMAND")
    _add_leaf(subparsers, "init", summary="create a project anchor here", handler=_handle_init, build=_build_init)
    _add_leaf(
        subparsers,
        "show",
        summary="describe the nearest project",
        handler=_handle_show,
        build=_build_show,
    )
    _add_leaf(
        subparsers,
        "import-v1",
        summary="import a legacy v1 project",
        handler=_handle_import_v1,
        build=_build_import_v1,
    )
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level ``project`` command."""

    parser = build_parser(f"{context.program} project")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    handler: Handler | None = getattr(arguments, "handler", None)
    if handler is None:
        getattr(arguments, "help_parser", parser).print_help()
        return 0
    try:
        return handler(arguments, context)
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(command(sys.argv[1:], CLIContext("httk", Path.cwd())))
