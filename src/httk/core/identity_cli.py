"""The core-owned ``httk init`` and ``httk identity`` commands.

These configure the per-user operator identities that live in
``identity.json``: :command:`httk init` establishes the first named default
identity, and :command:`httk identity` manages that same store. Future
per-user initialization will also live under :command:`httk init`. Both are
thin command-line wrappers over :mod:`httk.core.identity`.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from httk.core.cli import CLIContext
from httk.core.identity import (
    add_identity,
    configured_operator_identity,
    identity_config_path,
    identity_key_paths,
    identity_public_key,
    initialize_identity,
    read_identity_config,
    remove_identity,
    set_default_identity,
)

#: Everything a handler may raise that is an operator's problem rather than a
#: defect. Anything here is reported as ``PROGRAM: message`` and exits ``2``.
_ERRORS = (OSError, ValueError)


def _required(value: str | None, label: str, *, non_interactive: bool, default: str | None = None) -> str:
    """Return *value*, asking for it on a terminal and refusing without one."""

    if value:
        return value
    if non_interactive or not sys.stdin.isatty():
        raise ValueError(f"missing required value {label!r} in non-interactive operation")
    suffix = f" [{default}]" if default else ""
    entered = input(f"{label}{suffix}: ").strip()
    result = entered or default
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _identity_report(short: str, name: str, email: str, is_default: bool) -> dict[str, object]:
    seed_path, _ = identity_key_paths(short)
    return {
        "short": short,
        "name": name,
        "email": email,
        "public_key": identity_public_key(seed_path),
        "default": is_default,
    }


def init_command(argv: Sequence[str], context: CLIContext) -> int:
    """Set up httk for this user by establishing the default operator identity.

    This getting-started command is idempotent: once a default identity exists,
    it reports that setup without prompting or changing the identity store.
    Future per-user initialization will also live here.

    :param argv: Arguments following the ``init`` command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = argparse.ArgumentParser(
        prog=f"{context.program} init",
        description="Set up httk for this user and establish the default operator identity",
    )
    parser.add_argument("--name", metavar="NAME", help="the operator's name")
    parser.add_argument("--email", metavar="EMAIL", help="the operator's email address")
    parser.add_argument("--non-interactive", action="store_true", help="never prompt; refuse a missing value")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1

    try:
        current_identity = configured_operator_identity()
        if current_identity is not None:
            assert current_identity.short is not None
            print(
                json.dumps(
                    {
                        **_identity_report(
                            current_identity.short,
                            current_identity.name,
                            current_identity.email,
                            True,
                        ),
                        "created": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        name = _required(
            arguments.name,
            "name",
            non_interactive=arguments.non_interactive,
        )
        email = _required(
            arguments.email,
            "email",
            non_interactive=arguments.non_interactive,
        )
        created, identity = initialize_identity(name, email)
        assert identity.short is not None
        print(
            json.dumps(
                {
                    **_identity_report(identity.short, identity.name, identity.email, True),
                    "created": created,
                },
                indent=2,
                sort_keys=True,
            )
        )
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2
    return 0


def _handle_identity_add(arguments: argparse.Namespace) -> int:
    values = add_identity(arguments.short, arguments.name, arguments.email, make_default=arguments.default)
    is_default = values.get("default_identity") == arguments.short
    print(json.dumps(_identity_report(arguments.short, arguments.name, arguments.email, is_default)))
    return 0


def _handle_identity_list(arguments: argparse.Namespace) -> int:
    values = read_identity_config()
    raw = values.get("identities")
    identities: dict[str, dict[str, str]] = {}
    if isinstance(raw, Mapping):
        for short, item in raw.items():
            if isinstance(item, Mapping):
                identities[str(short)] = {"name": str(item.get("name", "")), "email": str(item.get("email", ""))}
    default = values.get("default_identity")
    default_short = default if isinstance(default, str) else None
    if "default_identity" in values and (default_short is None or default_short not in identities):
        print(f"warning: default identity {default!r} is not a configured identity", file=sys.stderr)
    reports = [
        _identity_report(short, identities[short]["name"], identities[short]["email"], short == default_short)
        for short in sorted(identities)
    ]
    if arguments.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for report in reports:
            print(
                f"{'*' if report['default'] else ' '} {report['short']}\t"
                f"{report['name']} <{report['email']}>\t{report['public_key']}"
            )
    return 0


def _handle_identity_default(arguments: argparse.Namespace) -> int:
    set_default_identity(arguments.short)
    print(identity_config_path())
    return 0


def _handle_identity_remove(arguments: argparse.Namespace) -> int:
    failed = False
    for short in arguments.short:
        try:
            remove_identity(short)
            seed_path, public_path = identity_key_paths(short)
            print(f"removed {short}; key files remain: {seed_path}, {public_path}")
        except _ERRORS as exc:
            print(f"identity {short}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


def _build_identity_parser(program: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=program,
        description="Create, list, select, and remove named operator identities",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    add = subparsers.add_parser("add", help="add a named operator identity")
    add.add_argument("short", metavar="SHORT", help="the short identity name ([a-z0-9][a-z0-9_-]*)")
    add.add_argument("--name", required=True, metavar="NAME", help="the operator's full name")
    add.add_argument("--email", required=True, metavar="EMAIL", help="the operator's email address")
    add.add_argument("--default", action="store_true", help="make this identity the default")
    add.set_defaults(handler=_handle_identity_add)

    listed = subparsers.add_parser("list", help="list named operator identities")
    listed.add_argument("--json", action="store_true", help="print the identities as JSON")
    listed.set_defaults(handler=_handle_identity_list)

    selected = subparsers.add_parser("default", help="select the default identity")
    selected.add_argument("short", metavar="SHORT", help="the configured identity short name")
    selected.set_defaults(handler=_handle_identity_default)

    removed = subparsers.add_parser("remove", help="remove named operator identities")
    removed.add_argument("short", metavar="SHORT", nargs="+", help="the configured identity short name")
    removed.set_defaults(handler=_handle_identity_remove)
    return parser


def identity_command(argv: Sequence[str], context: CLIContext) -> int:
    """Manage named operator identities.

    :param argv: Arguments following the ``identity`` command name.
    :param context: Root CLI invocation context.
    :return: Command exit status.
    """

    parser = _build_identity_parser(f"{context.program} identity")
    try:
        arguments = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    try:
        return int(arguments.handler(arguments))
    except _ERRORS as exc:
        print(f"{parser.prog}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(identity_command(sys.argv[1:], CLIContext("httk", Path.cwd())))
