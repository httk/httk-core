"""Command-line registry and command metadata."""

#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation; either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from ._base import _same_callable_reference, resolve_callable

if TYPE_CHECKING:
    from ..cli import CLIContext

CLIHandler = Callable[[Sequence[str], "CLIContext"], int]


@dataclass(frozen=True)
class CLICommand:
    """Store registration metadata for one top-level :command:`httk` command.

    :param name: The lowercase hyphen-separated command name.
    :param handler: The command callable or lazy reference.
    :param summary: The one-line command summary.
    """

    name: str
    handler: str | Callable[..., Any]
    summary: str

    def resolve(self) -> CLIHandler:
        """Import and return the registered command implementation.

        :return: The resolved command handler.
        """

        resolved = resolve_callable(self.handler)
        return cast(CLIHandler, resolved)


_CLI_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_CLI_RESERVED = frozenset({"help", "version"})
_cli_commands: dict[str, CLICommand] = {}
_cli_extensions: dict[str, list[str | Callable[..., Any]]] = {}


def register_cli_command(name: str, handler: str | Callable[..., Any], summary: str) -> None:
    """Register a lazy top-level :command:`httk` command.

    A handler is either a callable or a lazy ``"module:callable"`` reference
    with the contract ``(argv: Sequence[str], context: CLIContext) -> int``.
    Names use lowercase, hyphen-separated command syntax. Registration is
    intentionally strict: reserved names and duplicate registrations are
    errors rather than order-dependent overrides.

    :param name: The lowercase hyphen-separated command name.
    :param handler: The command callable or lazy ``"module:callable"`` reference.
    :param summary: The nonempty one-line command summary.
    :raises TypeError: If ``handler`` is neither callable nor a lazy reference.
    :raises ValueError: If the name, handler reference, summary, or registration is invalid.
    """

    if not isinstance(name, str) or _CLI_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid CLI command name: {name!r}")
    if name in _CLI_RESERVED:
        raise ValueError(f"reserved CLI command name: {name!r}")
    if name in _cli_commands:
        raise ValueError(f"CLI command is already registered: {name!r}")
    if not callable(handler) and not isinstance(handler, str):
        raise TypeError("CLI command handler must be callable or a 'module:callable' reference")
    if isinstance(handler, str):
        module_name, separator, attribute = handler.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("lazy CLI command handler must use 'module:callable' syntax")
    if not isinstance(summary, str) or not summary.strip() or "\n" in summary:
        raise ValueError("CLI command summary must be a nonempty single line")
    _cli_commands[name] = CLICommand(name=name, handler=handler, summary=summary.strip())


def known_cli_commands() -> list[str]:
    """Return registered top-level command names without resolving handlers.

    :return: Registered command names in sorted order.
    """

    return sorted(_cli_commands)


def cli_command(name: str) -> CLICommand | None:
    """Return command metadata without importing its implementation.

    :param name: The command name to look up.
    :return: Command metadata, or ``None`` if it is not registered.
    """

    return _cli_commands.get(name)


def register_cli_extension(command: str, provider: str | Callable[..., Any]) -> None:
    """Register a lazy leaf provider under a core-owned command group.

    A provider is either a callable or a lazy ``"module:callable"`` reference
    with the contract
    ``provider(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None``.
    It adds parsers to the group's subparsers whose ``set_defaults(handler=...)``
    handlers follow the group's ``(argparse.Namespace, CLIContext) -> int``
    contract; the mounting group owns error dispatch. Validation mirrors
    :func:`register_cli_command`: reserved names and duplicate ``(command,
    provider)`` registrations are errors rather than order-dependent overrides.

    :param command: The lowercase hyphen-separated group name to extend.
    :param provider: The provider callable or lazy ``"module:callable"`` reference.
    :raises TypeError: If ``provider`` is neither callable nor a lazy reference.
    :raises ValueError: If the command name, provider reference, or registration is invalid.
    """

    if not isinstance(command, str) or _CLI_NAME.fullmatch(command) is None:
        raise ValueError(f"invalid CLI command name: {command!r}")
    if command in _CLI_RESERVED:
        raise ValueError(f"reserved CLI command name: {command!r}")
    if not callable(provider) and not isinstance(provider, str):
        raise TypeError("CLI extension provider must be callable or a 'module:callable' reference")
    if isinstance(provider, str):
        module_name, separator, attribute = provider.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("lazy CLI extension provider must use 'module:callable' syntax")
    providers = _cli_extensions.setdefault(command, [])
    if any(_same_callable_reference(existing, provider) for existing in providers):
        raise ValueError(f"CLI extension is already registered for {command!r}: {provider!r}")
    providers.append(provider)


def cli_extensions(command: str) -> tuple[Callable[..., Any], ...]:
    """Return resolved leaf providers registered for a command group.

    Lazy ``"module:callable"`` references are imported and resolved at call
    time, mirroring :meth:`CLICommand.resolve`; a broken reference propagates
    the import or attribute error.

    :param command: The group name to look up.
    :return: Resolved providers in registration order.
    """

    return tuple(resolve_callable(provider) for provider in _cli_extensions.get(command, ()))
