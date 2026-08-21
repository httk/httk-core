"""The core-owned ``httk plugin`` command."""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from httk.core.cli import CLIContext
from httk.core.project.templates import parse_template_manifest

from . import (
    build_plugin,
    install_plugin,
    installed_plugins,
    plugin_program,
    shims_home,
    uninstall_plugin,
)

#: Everything a handler may raise that is an operator's problem rather than a
#: defect. Anything here is reported as ``PROGRAM: message`` and exits ``2``.
_ERRORS = (OSError, ValueError, RuntimeError)

#: The handler contract every plugin subcommand honors.
Handler = Callable[[argparse.Namespace, CLIContext], int]


def _field(name: str, value: object) -> str:
    """Render one name/value line of a human-readable description."""

    return f"{name:<22}{value}"


def _find_plugin(name: str):
    for plugin in installed_plugins():
        if plugin.name == name:
            return plugin
    raise ValueError(f"plugin {name!r} is not installed")


def _first_error(exc: Exception) -> str:
    return str(exc).splitlines()[0] or type(exc).__name__


def _list_value(description: dict[str, object], name: str) -> list[object]:
    value = description.get(name)
    if not isinstance(value, list):
        raise ValueError(f"plugin description field {name!r} must be a list")
    return value


def _template_details(plugin) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for member in plugin.manifest.templates:
        try:
            template = parse_template_manifest(plugin.root / PurePosixPath(member))
        except (OSError, ValueError) as exc:
            details.append({"directory": member, "invalid": _first_error(exc)})
        else:
            details.append({"id": template.id, "description": template.description})
    return details


def _description(plugin) -> dict[str, object]:
    description = dict(plugin.metadata)
    description["templates"] = _template_details(plugin)
    description["workflows"] = list(plugin.manifest.workflows)
    description["programs"] = [
        {"name": program.name, "file": program.file, "description": program.description}
        for program in plugin.manifest.programs
    ]
    return description


def _render(description: dict[str, object]) -> str:
    """Render one plugin description as readable lines."""

    lines = [
        _field("name", description.get("name")),
        _field("description", description.get("description") or ""),
        _field("source", description.get("source")),
        _field("installed_at", description.get("installed_at")),
        _field("built", description.get("built")),
        "templates:",
    ]
    for template in _list_value(description, "templates"):
        assert isinstance(template, dict)
        if "invalid" in template:
            lines.append(f"  {template['directory']}: invalid ({template['invalid']})")
        else:
            lines.append(f"  {template['id']}  {template.get('description') or ''}")
    lines.append("workflows:")
    lines.extend(f"  {workflow}" for workflow in _list_value(description, "workflows"))
    lines.append("programs:")
    for program in _list_value(description, "programs"):
        assert isinstance(program, dict)
        lines.append(f"  {program['name']}  {program['file']}  {program.get('description') or ''}")
    return "\n".join(lines)


def _handle_install(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Install plugin sources in order, continuing after failures."""

    failed = False
    for source in arguments.sources:
        try:
            installed = install_plugin(source, force=arguments.force)
            suffix = " (built)" if installed.metadata.get("built") is True else ""
            print(f"Installed plugin {installed.name!r} from {source}{suffix}")
            if str(shims_home()) not in os.environ.get("PATH", "").split(os.pathsep):
                print(f"note: add {shims_home()} to PATH to run plugin programs by name")
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} plugin: {source}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_list(arguments: argparse.Namespace, context: CLIContext) -> int:
    """List installed plugins."""

    plugins = installed_plugins()
    if not plugins:
        print("no plugins installed")
        return 0
    for plugin in plugins:
        print(f"{plugin.name}  {plugin.manifest.description or ''}")
    return 0


def _handle_show(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Describe installed plugins."""

    descriptions: list[dict[str, object]] = []
    failed = False
    for name in arguments.names:
        try:
            descriptions.append(_description(_find_plugin(name)))
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} plugin: {name}: {exc}", file=sys.stderr)
    if arguments.json:
        print(json.dumps(descriptions, indent=2, sort_keys=True))
    else:
        for description in descriptions:
            print(f"=== {description.get('name')} ===")
            print(_render(description))
    return 1 if failed else 0


def _handle_uninstall(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Uninstall installed plugins."""

    failed = False
    for name in arguments.names:
        try:
            uninstall_plugin(name)
            print(f"Uninstalled plugin {name!r}")
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} plugin: {name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_build(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Build installed plugins."""

    failed = False
    for name in arguments.names:
        try:
            build_plugin(name)
            print(f"Built plugin {name!r}")
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} plugin: {name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_path(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Print installed plugin program paths."""

    failed = False
    for name in arguments.names:
        try:
            print(plugin_program(name, arguments.program))
        except _ERRORS as exc:
            failed = True
            print(f"{context.program} plugin: {name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def _handle_run(arguments: argparse.Namespace, context: CLIContext) -> int:
    """Run one installed plugin program with the remaining arguments."""

    path = plugin_program(arguments.name, arguments.program)
    return subprocess.run([str(path), *arguments.args], check=False).returncode


def _build_install(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("sources", metavar="SOURCE", nargs="+", help="plugin sources to install")
    parser.add_argument("--force", action="store_true", help="replace an installed plugin with the same name")


def _build_names(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("names", metavar="NAME", nargs="+", help="installed plugin names")


def _build_name(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("name", metavar="NAME", help="the installed plugin name")


def _build_show(parser: argparse.ArgumentParser) -> None:
    _build_names(parser)
    parser.add_argument("--json", action="store_true", help="print the description as one JSON document")


def _build_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--program", required=True, metavar="PROGRAM", help="the declared program name")
    _build_names(parser)


def _build_run(parser: argparse.ArgumentParser) -> None:
    _build_name(parser)
    parser.add_argument("program", metavar="PROGRAM", help="the declared program name")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.REMAINDER, help="arguments for the program")


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
    """Build the core-owned plugin command tree.

    :param program: Program name used by the parser in help and errors.
    :return: Configured plugin command parser.
    """

    parser = argparse.ArgumentParser(prog=program, description="Install and manage httk plugins")
    parser.set_defaults(handler=None, help_parser=parser)
    subparsers = parser.add_subparsers(metavar="COMMAND")
    _add_leaf(
        subparsers,
        "install",
        summary="install a plugin",
        handler=_handle_install,
        build=_build_install,
    )
    _add_leaf(subparsers, "list", summary="list installed plugins", handler=_handle_list, build=lambda parser: None)
    _add_leaf(subparsers, "show", summary="describe an installed plugin", handler=_handle_show, build=_build_show)
    _add_leaf(
        subparsers,
        "uninstall",
        summary="uninstall a plugin",
        handler=_handle_uninstall,
        build=_build_names,
    )
    _add_leaf(subparsers, "build", summary="build installed plugins", handler=_handle_build, build=_build_names)
    _add_leaf(subparsers, "path", summary="print a plugin program path", handler=_handle_path, build=_build_path)
    _add_leaf(subparsers, "run", summary="run a plugin program", handler=_handle_run, build=_build_run)
    return parser


def command(argv: Sequence[str], context: CLIContext) -> int:
    """Handle the registered top-level plugin command.

    :param argv: Arguments following the plugin command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = build_parser(f"{context.program} plugin")
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
