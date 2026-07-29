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
from threading import Lock
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

#: Domain adapters selected by a loader's neutral payload ``"format"`` tag.
format_adapters = PluginRegistry()
_format_adapter_lock = Lock()


def _same_callable_reference(left: str | Callable[..., Any], right: str | Callable[..., Any]) -> bool:
    """Compare lazy references by value and callable registrations by identity."""
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right
    return left is right


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


def register_format_adapter(
    *,
    name: str,
    adapter: str | Callable[..., Any],
    formats: Sequence[str],
) -> None:
    """Register one lazy adapter for each neutral payload format in ``formats``.

    ``adapter`` may be a callable or a lazy ``"module:callable"`` reference.
    A format tag has one owner: registering it again raises an error naming both
    the existing and attempted registrants.
    """
    if isinstance(formats, str):
        raise ValueError("formats must be a sequence of nonempty format-tag strings, not a string")
    try:
        format_tags = tuple(formats)
    except TypeError as exc:
        raise ValueError("formats must be a sequence of nonempty format-tag strings") from exc
    seen: set[str] = set()
    for format_tag in format_tags:
        if not isinstance(format_tag, str) or not format_tag:
            raise ValueError(f"format tags must be nonempty strings, got {format_tag!r}")
        if format_tag in seen:
            raise ValueError(f"format adapter format tag is listed more than once: {format_tag!r}")
        seen.add(format_tag)
    with _format_adapter_lock:
        missing: list[str] = []
        for format_tag in format_tags:
            existing = format_adapters.get(format_tag)
            if existing is None:
                missing.append(format_tag)
                continue
            if existing.name == name and _same_callable_reference(existing.handler, adapter):
                continue
            raise ValueError(
                f"format tag {format_tag!r} is already registered by {existing.name!r}; cannot register {name!r}"
            )
        for format_tag in missing:
            format_adapters.register(key=format_tag, handler=adapter, name=name)


def known_format_adapters() -> dict[str, str]:
    """Return format tags mapped to their registered adapter names."""
    known: dict[str, str] = {}
    for format_tag, spec in sorted(format_adapters.items()):
        if spec.name is not None:
            known[format_tag] = spec.name
    return known


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


_entry_records: dict[str, tuple[str, str | None]] = {}


def register_entry_record(*, name: str, record: str, definition_id: str | None = None) -> None:
    """Register a lazy record-class reference and optional definition IRI."""
    if name in _entry_records:
        raise ValueError(f"entry record is already registered: {name!r}")
    _entry_records[name] = (record, definition_id)


def known_entry_records() -> list[str]:
    return sorted(_entry_records)


def entry_record_info(name: str) -> tuple[str, str | None]:
    """Return a record reference and definition IRI without importing it."""
    try:
        return _entry_records[name]
    except KeyError as exc:
        known = ", ".join(known_entry_records()) or "(none)"
        raise ValueError(f"No entry record registered for {name!r}. Known: {known}") from exc


def resolve_entry_record(name: str) -> type:
    """Import and return a registered record class."""
    resolved = resolve_callable(entry_record_info(name)[0])
    if not isinstance(resolved, type):
        raise TypeError(f"Resolved entry record {name!r} to non-class object {resolved!r}")
    return resolved


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
