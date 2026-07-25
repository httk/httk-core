#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
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

from ._plugins import PluginRegistry, resolve_callable

if TYPE_CHECKING:
    from .cli import CLIContext

#: Loaders selected by file *extension* (keys are lower-case ``".ext"`` suffixes).
loaders = PluginRegistry()

#: Loaders selected by exact *basename* (keys are lower-case basenames such as
#: ``"contcar"``). A separate key namespace from :data:`loaders` so an
#: extension-less file (``POSCAR``, ``CONTCAR``) can still dispatch by name.
loader_filenames = PluginRegistry()


def register_loader(
    *,
    name: str,
    loader: str,
    extensions: tuple[str, ...] = (),
    filenames: tuple[str, ...] = (),
) -> None:
    """Register a loader under one or more file ``extensions`` and/or ``filenames``.

    ``extensions`` are matched (case-insensitively) against a file's suffix, e.g.
    ``".cif"``. ``filenames`` are exact basenames matched (case-insensitively)
    against a file's name with any recognized compression suffix stripped, e.g.
    ``"POSCAR"`` matches ``POSCAR``, ``poscar``, and ``POSCAR.bz2``.
    """
    for ext in extensions:
        loaders.register(key=ext.lower(), handler=loader, name=name)
    for filename in filenames:
        loader_filenames.register(key=filename.lower(), handler=loader, name=name)


def known_extensions() -> list[str]:
    return loaders.keys()


def known_filenames() -> list[str]:
    return loader_filenames.keys()


entry_providers = PluginRegistry()


def register_entry_provider(*, name: str, factory: str) -> None:
    """Register an :class:`~httk.core.entry_provider.EntryProvider` factory under ``name``.

    ``factory`` is a lazy ``"module:callable"`` reference to a callable that
    constructs a provider (providers need data, so applications call the factory
    themselves; the registry only records how to reach it). This mirrors
    ``register_loader``.
    """
    entry_providers.register(key=name, handler=factory, name=name)


def known_entry_providers() -> list[str]:
    return entry_providers.keys()


CLIHandler = Callable[[Sequence[str], "CLIContext"], int]


@dataclass(frozen=True)
class CLICommand:
    """Registration metadata for one top-level :command:`httk` command."""

    name: str
    handler: str | Callable[..., Any]
    summary: str

    def resolve(self) -> CLIHandler:
        """Import and return the registered command implementation."""

        resolved = resolve_callable(self.handler)
        return cast(CLIHandler, resolved)


_CLI_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_CLI_RESERVED = frozenset({"help", "version"})
_cli_commands: dict[str, CLICommand] = {}


def register_cli_command(name: str, handler: str | Callable[..., Any], summary: str) -> None:
    """Register a lazy top-level :command:`httk` command.

    A handler is either a callable or a lazy ``"module:callable"`` reference
    with the contract ``(argv: Sequence[str], context: CLIContext) -> int``.
    Names use lowercase, hyphen-separated command syntax. Registration is
    intentionally strict: reserved names and duplicate registrations are
    errors rather than order-dependent overrides.
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
    """Return registered top-level command names without resolving handlers."""

    return sorted(_cli_commands)


def cli_command(name: str) -> CLICommand | None:
    """Return command metadata without importing its implementation."""

    return _cli_commands.get(name)
