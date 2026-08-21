"""The core-owned ``httk project`` command.

``httk project`` owns the anchor: ``init`` creates one (like ``git init``),
``show`` describes it, ``seal`` creates a signed redistribution,
``verify-seal`` checks one, and ``import-v1`` migrates a legacy project.
"""

import argparse
import json
import shutil
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
from .seal import seal_project, verify_seal
from .templates import available_templates, check_parameters, instantiate_template, resolve_template

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


def describe_project(root: str | Path | None = None) -> dict[str, object]:
    """Describe one project's anchor.

    :param root: Project root, or None to discover the nearest project.
    :return: JSON-ready description of project metadata and trust keys.
    :raises ValueError: If no project exists or its metadata is invalid.
    """

    project = require_project(root)
    metadata = read_project(project)
    own = pinned_project_key(metadata)
    trusted = trusted_project_keys(metadata)
    seed = project / PROJECT_DIRECTORY / "keys" / "project.seed"
    description: dict[str, object] = {
        "format": "httk-project-description",
        "format_version": 2,
        "root": str(project),
        "project": {
            "project_id": metadata.get("project_id"),
            "name": metadata.get("name"),
            "description": metadata.get("description"),
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
        _field("key_pinned", "yes" if keys.get("pinned") else "no"),
        _field("key_fingerprint", public.get("fingerprint") or "-"),
        _field("trusted_keys", len(keys.get("trusted_keys", []))),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Built-in leaves
# ---------------------------------------------------------------------------


def _init_one(path: Path, arguments: argparse.Namespace) -> None:
    """Create one project anchor at PATH, refusing an existing project."""

    if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        raise ValueError(f"{path} is already an httk project")
    if not arguments.template:
        metadata = initialize_project(
            path,
            name=arguments.name or path.name,
            description=arguments.description,
        )
        print(f"Initialized httk project {metadata['name']!r} in {path / PROJECT_DIRECTORY}")
        return

    template = resolve_template(arguments.template)
    supplied: dict[str, object] = {}
    for value in arguments.parameter or []:
        if "=" not in value:
            raise ValueError(f"invalid template parameter {value!r}; expected NAME=VALUE")
        name, raw = value.split("=", 1)
        try:
            supplied[name] = json.loads(raw)
        except json.JSONDecodeError:
            supplied[name] = raw
    parameters = check_parameters(template, supplied)
    was_fresh = not path.exists() or (path.is_dir() and not any(path.iterdir()))

    try:
        initialize_project(
            path,
            name=arguments.name or path.name,
            description=arguments.description,
        )
        project = describe_project(path)["project"]
        assert isinstance(project, dict)
        notes = instantiate_template(
            template,
            path,
            parameters,
            project_info={
                "name": project.get("name"),
                "description": project.get("description"),
                "project_id": project.get("project_id"),
            },
        )
    except _ERRORS as exc:
        if was_fresh:
            if path.is_dir():
                shutil.rmtree(path)
        else:
            raise ValueError(
                f"{exc}; partial state left in {path} (httk_project/ and any copied template files)"
            ) from exc
        raise
    print(f"Initialized httk project {project['name']!r} in {path / PROJECT_DIRECTORY}")
    for note in notes:
        print(f"note: {note}")


def _handle_init(arguments: argparse.Namespace, context: CLIContext) -> int:
    if arguments.list_templates:
        templates = available_templates()
        if not templates:
            print("no templates available")
        else:
            for plugin, template in templates:
                print(f"{plugin}:{template.id}  {template.description or ''}")
            print("templates can also be given as a directory path")
        return 0
    failed = False
    for raw_path in arguments.paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            _init_one(path, arguments)
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_import_v1(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Import a legacy v1 project into a new v2 anchor."""

    failed = False
    for raw_path in arguments.paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            if (path / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
                raise ValueError(f"{path} is already an httk project")
            source = Path(arguments.source or path / "ht.project").expanduser().resolve()
            import_v1_project(path, source=source, name=arguments.name)
            print(f"imported {source} -> {path / PROJECT_DIRECTORY}")
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_show(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Describe the nearest project: its metadata and keys."""

    descriptions: list[dict[str, object]] = []
    failed = False
    paths = arguments.paths or [str(context.cwd)]
    for raw_path in paths:
        label: str | Path = raw_path
        try:
            path = Path(raw_path).expanduser().resolve()
            label = path
            description = describe_project(path)
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {label}: {exc}", file=sys.stderr)
            continue
        descriptions.append(description)
        if not arguments.json:
            print(f"=== {path} ===")
            print(_render(description))
    if arguments.json:
        print(json.dumps(descriptions, indent=2, sort_keys=True))
    return 1 if failed else 0


def _handle_seal(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Seal the nearest project tree into a signed redistribution ZIP."""

    output = seal_project(Path(arguments.out_zip).expanduser().resolve(), context.cwd)
    print(f"sealed project to {output}")
    return 0


def _handle_verify_seal(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Verify a signed redistribution ZIP and print its signer."""

    failed = False
    for raw_path in arguments.zip_paths:
        try:
            report = verify_seal(
                raw_path,
                expect_key=arguments.expect_key,
                trusted_keys=arguments.trusted_keys,
            )
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} project: {raw_path}: {exc}", file=sys.stderr)
            continue
        print(f"=== {raw_path} ===")
        print(report["status"])
        print(f"public_key: {report['public_key']}")
        print(f"fingerprint: {report['fingerprint']}")
    return 1 if failed else 0


def _build_init(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="directories to make projects",
    )
    parser.add_argument("--name", metavar="NAME", help="the project name (default: the directory name)")
    parser.add_argument("--description", metavar="TEXT", default="", help="a one-line description")
    parser.add_argument("--template", metavar="SELECTOR", help="instantiate a project template")
    parser.add_argument(
        "--parameter",
        action="append",
        metavar="NAME=VALUE",
        help="set a template parameter (repeatable)",
    )
    parser.add_argument("--list-templates", action="store_true", help="list available project templates")


def _build_show(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        help="projects to describe (default: the nearest project of the working directory)",
    )
    parser.add_argument("--json", action="store_true", help="print the description as one JSON document")


def _build_import_v1(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="+",
        help="projects to import",
    )
    parser.add_argument("--source", metavar="DIR", help="the v1 project directory (default: PATH/ht.project)")
    parser.add_argument("--name", metavar="NAME", help="the imported project name")


def _build_seal(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("out_zip", metavar="OUT.ZIP", help="destination signed redistribution ZIP")


def _build_verify_seal(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("zip_paths", metavar="ZIP", nargs="+", help="signed redistribution ZIPs to verify")
    parser.add_argument("--expect-key", metavar="FINGERPRINT", help="require this signer fingerprint")
    parser.add_argument(
        "--trusted-key",
        dest="trusted_keys",
        metavar="FINGERPRINT",
        action="append",
        default=[],
        help="trust this signer fingerprint",
    )


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
    """Build the core-owned project command tree.

    :param program: Program name used by the parser in help and errors.
    :return: Configured project command parser.
    """

    parser = argparse.ArgumentParser(prog=program, description="Create and inspect httk projects")
    parser.set_defaults(handler=None, help_parser=parser)
    subparsers = parser.add_subparsers(dest="subcommand", metavar="COMMAND")
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
    _add_leaf(
        subparsers, "seal", summary="create a signed project redistribution", handler=_handle_seal, build=_build_seal
    )
    _add_leaf(
        subparsers,
        "verify-seal",
        summary="verify a signed project redistribution",
        handler=_handle_verify_seal,
        build=_build_verify_seal,
    )
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level project command.

    :param argv: Arguments following the project command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = build_parser(f"{context.program} project")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    try:
        if arguments.subcommand == "init":
            if arguments.list_templates:
                if (
                    arguments.paths
                    or arguments.name
                    or arguments.description
                    or arguments.template
                    or arguments.parameter
                ):
                    parser.error("--list-templates cannot be combined with PATH or project/template options")
            elif not arguments.paths:
                parser.error("init requires at least one PATH")
            elif arguments.name and len(arguments.paths) != 1:
                parser.error("--name requires exactly one PATH")
            elif arguments.parameter and not arguments.template:
                parser.error("--parameter requires --template")
        elif arguments.subcommand == "import-v1" and (arguments.source or arguments.name) and len(arguments.paths) != 1:
            parser.error("--source and --name require exactly one PATH")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
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
