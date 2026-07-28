"""The umbrella ``httk project`` command and its extension registry.

``httk project`` owns the anchor: ``init`` creates one (like ``git init``) and
``show`` describes it. It is deliberately extensible. A capability that layers
on top of the anchor — *httk-workflow* contributes signed manifests, a doctor,
and the workspace rows of ``show`` — registers into this command rather than
adding a parallel one, so an operator sees a single ``httk project`` whose leaves
come from whatever is installed.

The registration machinery mirrors :func:`httk.core.register_cli_command`: a
capability registers *lazily*, by ``"module:callable"`` reference, from its
``httk.handlers.*`` package during core plugin discovery, and nothing heavy is
imported until ``httk project`` actually runs. Registrations are strict —
reserved names and duplicates are errors — and the command tree is assembled in
a stable order.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from httk.core._plugins import resolve_callable
from httk.core.cli_context import CLIContext

from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
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

#: The two built-in leaves. An extension may not shadow either of them.
_RESERVED = frozenset({"init", "show"})
_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

#: A callable, or a lazy ``"module:callable"`` reference to one. A capability
#: registers by reference so nothing heavy is imported until the command runs.
CallableRef = str | Callable[..., object]
#: The handler contract every project subcommand honors, the same one the root
#: :command:`httk` commands use.
Handler = Callable[[argparse.Namespace, CLIContext], int]
#: A builder declares one subcommand's arguments (and, for a group, its own
#: nested subcommands) on the parser it is given.
ParserBuilder = Callable[[argparse.ArgumentParser], None]


@dataclass(frozen=True)
class ProjectShowSection:
    """One capability's contribution to ``httk project show``.

    *json* is merged into the top level of the ``--json`` description; *rows* are
    appended, in order, to the human-readable listing as ``label``/``value``
    pairs.
    """

    json: dict[str, object] = field(default_factory=dict)
    rows: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _Subcommand:
    """Registration metadata for one extension subcommand of ``httk project``."""

    name: str
    build_parser: CallableRef
    handler: CallableRef | None
    summary: str
    description: str


_subcommands: dict[str, _Subcommand] = {}
_show_sections: dict[str, CallableRef] = {}


def register_project_subcommand(
    name: str,
    build_parser: CallableRef,
    handler: CallableRef | None = None,
    *,
    summary: str = "",
    description: str = "",
) -> None:
    """Register one lazy subcommand of ``httk project``.

    *build_parser* is a callable — or a ``"module:callable"`` reference — that
    receives the subcommand's :class:`argparse.ArgumentParser` and declares its
    arguments on it. A leaf passes *handler*, the ``(argv, context) -> int``
    function that runs it; a group passes ``handler=None`` and sets the handler
    of each of its own nested leaves inside *build_parser*.

    Registration is strict: names are lowercase and hyphenated, the built-in
    ``init`` and ``show`` cannot be shadowed, and a duplicate name is an error
    rather than an order-dependent override.
    """

    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise ValueError(f"invalid project subcommand name: {name!r}")
    if name in _RESERVED:
        raise ValueError(f"reserved project subcommand name: {name!r}")
    if name in _subcommands:
        raise ValueError(f"project subcommand is already registered: {name!r}")
    _subcommands[name] = _Subcommand(
        name=name,
        build_parser=build_parser,
        handler=handler,
        summary=summary.strip(),
        description=description.strip() or summary.strip(),
    )


def register_project_show_section(name: str, section: CallableRef) -> None:
    """Register one contributor to ``httk project show``.

    *section* is a callable — or a ``"module:callable"`` reference — invoked as
    ``section(root, verify=...)`` with the discovered project root and expected
    to return a :class:`~httk.core.project.cli.ProjectShowSection`. Sections are rendered in stable
    order by *name*; a duplicate name is an error.
    """

    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise ValueError(f"invalid project show section name: {name!r}")
    if name in _show_sections:
        raise ValueError(f"project show section is already registered: {name!r}")
    _show_sections[name] = section


def known_project_subcommands() -> list[str]:
    """Return the registered extension subcommand names, in stable order."""

    return sorted(_subcommands)


def known_project_show_sections() -> list[str]:
    """Return the registered show-section names, in stable order."""

    return sorted(_show_sections)


def _key_record(value: str) -> dict[str, object]:
    return {"public_key": value, "fingerprint": key_fingerprint(value)}


def _field(name: str, value: object) -> str:
    """Render one name/value line of a human-readable description."""

    return f"{name:<22}{value}"


def describe_project(
    root: str | Path | None = None,
    *,
    verify: bool = True,
) -> tuple[dict[str, object], list[tuple[str, str]]]:
    """Describe one project's anchor, merging every registered show section.

    Returns the JSON description and the extra human-readable rows the sections
    contributed; the anchor's own rows are added when the result is rendered.
    """

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
    rows: list[tuple[str, str]] = []
    for name in known_project_show_sections():
        section = resolve_callable(_show_sections[name])(project, verify=verify)
        if not isinstance(section, ProjectShowSection):
            raise TypeError(f"project show section {name!r} did not return a ProjectShowSection")
        description.update(section.json)
        rows.extend(section.rows)
    return description, rows


def _render(description: dict[str, object], extra_rows: Sequence[tuple[str, str]]) -> str:
    """Render one anchor description, and its sections, as readable lines."""

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
    lines.extend(_field(label, value) for label, value in extra_rows)
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


def _handle_show(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Describe the nearest project: its metadata, keys, and every section."""

    description, rows = describe_project(arguments.path or context.cwd, verify=not arguments.no_verify)
    if arguments.json:
        print(json.dumps(description, indent=2, sort_keys=True))
    else:
        print(_render(description, rows))
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


# ---------------------------------------------------------------------------
# Assembly and dispatch
# ---------------------------------------------------------------------------


def _add_leaf(
    subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]",
    name: str,
    *,
    summary: str,
    handler: Handler,
    build: ParserBuilder,
) -> None:
    parser = subparsers.add_parser(name, help=summary, description=summary)
    parser.set_defaults(handler=handler, help_parser=parser)
    build(parser)


def build_parser(program: str) -> argparse.ArgumentParser:
    """Build the whole ``httk project`` tree, including registered extensions."""

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
    for name in known_project_subcommands():
        spec = _subcommands[name]
        child = subparsers.add_parser(name, help=spec.summary or None, description=spec.description or None)
        handler = resolve_callable(spec.handler) if spec.handler is not None else None
        child.set_defaults(handler=handler, help_parser=child)
        resolve_callable(spec.build_parser)(child)
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
