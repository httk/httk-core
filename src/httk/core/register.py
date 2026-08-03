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


import dataclasses
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from threading import Lock
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from ._plugins import PluginRegistry, resolve_callable

if TYPE_CHECKING:
    from .cli import CLIContext
    from .property_definitions import EntryTypeDefinition, PropertyDefinition

#: Loaders selected by file *extension* (keys are lower-case ``".ext"`` suffixes).
loaders = PluginRegistry()

#: Loaders selected by exact *basename* (keys are lower-case basenames such as
#: ``"contcar"``). A separate key namespace from :data:`loaders` so an
#: extension-less file (``POSCAR``, ``CONTCAR``) can still dispatch by name.
loader_filenames = PluginRegistry()

#: Domain adapters selected by a loader's neutral payload ``"format"`` tag.
format_adapters = PluginRegistry()
_format_adapter_lock = Lock()

#: Writers selected by file extension or exact basename.
writers = PluginRegistry()
writer_filenames = PluginRegistry()
writer_formats = PluginRegistry()
_writer_formats: dict[tuple[int, str], str] = {}
_writers_by_format: dict[str, tuple[PluginRegistry, str]] = {}
format_serializers = PluginRegistry()
_format_serializer_lock = Lock()


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


def register_writer(
    *,
    name: str,
    writer: str | Callable[..., Any],
    format: str,
    extensions: tuple[str, ...] = (),
    filenames: tuple[str, ...] = (),
) -> None:
    """Register a writer under one or more extensions and/or exact basenames."""
    if not isinstance(format, str) or not format:
        raise ValueError(f"writer format must be a nonempty string, got {format!r}")
    keys = [(writers, extension.lower()) for extension in extensions]
    keys += [(writer_filenames, filename.lower()) for filename in filenames]
    existing = _writers_by_format.get(format)
    if existing is not None:
        old = existing[0].get(existing[1])
        if old is not None and not _same_callable_reference(old.handler, writer):
            raise ValueError(f"writer format {format!r} is already registered by {old.name!r}")
    if not keys:
        writer_formats.register(key=format, handler=writer, name=name)
        _writer_formats[(id(writer_formats), format)] = format
        _reindex_writer_format(format)
        return
    affected_formats = {format}
    for registry, key in keys:
        old_format = _writer_formats.get((id(registry), key))
        if old_format is not None:
            affected_formats.add(old_format)
        registry.register(key=key, handler=writer, name=name)
        _writer_formats[(id(registry), key)] = format
    for affected_format in affected_formats:
        _reindex_writer_format(affected_format)


def known_writers() -> list[str]:
    return sorted(set(writers.keys()) | set(writer_filenames.keys()))


def _reindex_writer_format(format: str) -> None:
    for registry in (writers, writer_filenames, writer_formats):
        for key in registry.keys():  # noqa: SIM118 — PluginRegistry exposes keys(), not mapping iteration.
            if _writer_formats.get((id(registry), key)) == format:
                _writers_by_format[format] = (registry, key)
                return
    _writers_by_format.pop(format, None)


def _writer_for_format(format: str) -> tuple[PluginRegistry, str] | None:
    return _writers_by_format.get(format)


def _writer_format(registry: PluginRegistry, key: str) -> str:
    return _writer_formats[(id(registry), key)]


def register_format_serializer(*, format: str, serializer: str | Callable[..., Any]) -> None:
    """Register one lazy serializer for a neutral payload format tag."""
    if not isinstance(format, str) or not format:
        raise ValueError(f"format tag must be a nonempty string, got {format!r}")
    with _format_serializer_lock:
        existing = format_serializers.get(format)
        if existing is not None:
            if _same_callable_reference(existing.handler, serializer):
                return
            raise ValueError(f"format serializer {format!r} is already registered")
        format_serializers.register(key=format, handler=serializer, name=format)


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


_entry_type_definitions: dict[str, str] = {}
_property_definitions: dict[str, str] = {}


def register_entry_type_definition(*, definition_id: str, resource: str) -> None:
    """Register one resource for an entry-type definition IRI."""
    if definition_id in _entry_type_definitions:
        raise ValueError(f"entry-type definition is already registered: {definition_id!r}")
    _entry_type_definitions[definition_id] = resource


def known_entry_type_definitions() -> list[str]:
    return sorted(_entry_type_definitions)


def register_property_definition(*, definition_id: str, resource: str) -> None:
    """Register one resource for a property definition IRI."""
    if definition_id in _property_definitions:
        raise ValueError(f"property definition is already registered: {definition_id!r}")
    _property_definitions[definition_id] = resource


def known_property_definitions() -> list[str]:
    return sorted(_property_definitions)


def _resource(resource: str) -> dict[str, Any]:
    package, separator, filename = resource.partition(":")
    if not separator or not package or not filename:
        raise ValueError(f"Invalid registry resource {resource!r}; expected 'package:filename.json'")
    return cast(dict[str, Any], json.loads(files(package).joinpath(filename).read_text(encoding="utf-8")))


@cache
def load_entry_type_definition(definition_id: str) -> "EntryTypeDefinition":
    """Load and verify a registered entry-type definition resource."""
    try:
        resource = _entry_type_definitions[definition_id]
    except KeyError as exc:
        known = ", ".join(known_entry_type_definitions()) or "(none)"
        raise ValueError(f"No entry-type definition registered for {definition_id!r}. Known: {known}") from exc
    from .property_definitions import EntryTypeDefinition

    document = _resource(resource)
    definition = EntryTypeDefinition.from_optimade(definition_id.rsplit("/", 1)[-1], document)
    document_id = definition.definition_id
    if document_id != definition_id:
        raise ValueError(
            f"Entry-type definition registration IRI {definition_id!r} does not match document $id {document_id!r}"
        )
    return definition


@cache
def load_property_definition(definition_id: str) -> "PropertyDefinition":
    """Load and verify a registered property definition resource."""
    try:
        resource = _property_definitions[definition_id]
    except KeyError as exc:
        known = ", ".join(known_property_definitions()) or "(none)"
        raise ValueError(f"No property definition registered for {definition_id!r}. Known: {known}") from exc
    from .property_definitions import PropertyDefinition

    document = _resource(resource)
    name = document.get("name", definition_id.rsplit("/", 1)[-1])
    definition = PropertyDefinition.from_optimade(name, document)
    document_id = definition.definition_id
    if document_id != definition_id:
        raise ValueError(
            f"Property definition registration IRI {definition_id!r} does not match document $id {document_id!r}"
        )
    return definition


_entry_records: dict[str, tuple[str, str | None, str | None]] = {}


def register_entry_record(
    *, name: str, record: str, family: str | None = None, definition_id: str | None = None
) -> None:
    """Register a lazy record-class reference and optional family and definition IRI."""
    _validate_nonempty_optimade_string(name, label="entry record name")
    _validate_optimade_reference(record, label="entry record")
    if family is not None:
        _validate_nonempty_optimade_string(family, label="family")
        if family not in _entry_families:
            raise ValueError(f"No entry family registered for record {family!r}")
    if definition_id is not None:
        _validate_nonempty_optimade_string(definition_id, label="definition_id")
    if name in _entry_records:
        raise ValueError(f"entry record is already registered: {name!r}")
    _entry_records[name] = (record, family, definition_id)


def known_entry_records(family: str | None = None) -> list[str]:
    return sorted(
        name
        for name, (_, registered_family, _) in _entry_records.items()
        if family is None or family == registered_family
    )


def entry_record_info(name: str) -> tuple[str, str | None, str | None]:
    """Return record, family, and definition metadata without importing the record class."""
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
    params = getattr(resolved, "__dataclass_params__", None)
    if not dataclasses.is_dataclass(resolved) or params is None or not params.frozen:
        raise TypeError(f"Resolved entry record {name!r} to a non-frozen dataclass {resolved!r}")
    return resolved


_entry_families: dict[str, tuple[str, str | None]] = {}


def register_entry_family(*, name: str, family: str, definition_id: str | None = None) -> None:
    """Register a lazy entry-family class reference without importing it."""
    _validate_nonempty_optimade_string(name, label="entry family name")
    _validate_optimade_reference(family, label="entry family")
    if definition_id is not None:
        _validate_nonempty_optimade_string(definition_id, label="definition_id")
    if name in _entry_families:
        raise ValueError(f"entry family is already registered: {name!r}")
    _entry_families[name] = (family, definition_id)


def known_entry_families() -> list[str]:
    return sorted(_entry_families)


def entry_family_info(name: str) -> tuple[str, str | None]:
    """Return entry-family metadata without importing its class."""
    try:
        return _entry_families[name]
    except KeyError as exc:
        known = ", ".join(known_entry_families()) or "(none)"
        raise ValueError(f"No entry family registered for {name!r}. Known: {known}") from exc


def resolve_entry_family(name: str) -> type:
    """Import and return a registered entry-family class."""
    resolved = resolve_callable(entry_family_info(name)[0])
    if not isinstance(resolved, type):
        raise TypeError(f"Resolved entry family {name!r} to non-class object {resolved!r}")
    return resolved


def _validate_optimade_reference(reference: str, *, label: str) -> None:
    if not isinstance(reference, str):
        raise TypeError(f"{label} must be a 'module:attr' string")
    module_name, separator, attribute = reference.partition(":")
    if (
        not separator
        or reference.count(":") != 1
        or not module_name
        or not attribute
        or any(not part.isidentifier() for part in module_name.split("."))
        or not attribute.isidentifier()
    ):
        raise ValueError(f"{label} must use strict 'module:attr' syntax")


def _validate_nonempty_optimade_string(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty string without surrounding whitespace")


@dataclass(frozen=True)
class OptimadeEntryBinding:
    """Lazy typed handling for one exact OPTIMADE entry-type definition IRI."""

    name: str
    definition_id: str
    backend: str
    view: str
    property_decoders: Mapping[str, str] = field(default_factory=dict)
    query_fields: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _validate_nonempty_optimade_string(self.name, label="binding name")
        _validate_nonempty_optimade_string(self.definition_id, label="definition_id")
        _validate_optimade_reference(self.backend, label="backend")
        _validate_optimade_reference(self.view, label="view")
        if not isinstance(self.property_decoders, Mapping):
            raise TypeError("property_decoders must be a mapping of definition IRIs to lazy references")
        decoders: dict[str, str] = {}
        for definition_id, decoder in self.property_decoders.items():
            _validate_nonempty_optimade_string(definition_id, label="property decoder definition_id")
            _validate_optimade_reference(decoder, label=f"property decoder {definition_id!r}")
            decoders[definition_id] = decoder
        if self.query_fields is not None:
            if not isinstance(self.query_fields, tuple):
                raise TypeError("query_fields must be a tuple of property-definition IRIs or None")
            seen: set[str] = set()
            for definition_id in self.query_fields:
                _validate_nonempty_optimade_string(definition_id, label="query field definition_id")
                if definition_id in seen:
                    raise ValueError(f"query field is listed more than once: {definition_id!r}")
                seen.add(definition_id)
        object.__setattr__(self, "property_decoders", MappingProxyType(decoders))

    def resolve_backend(self) -> type:
        """Import and return this binding's backend class on demand."""

        resolved = resolve_callable(self.backend)
        if not isinstance(resolved, type):
            raise TypeError(f"Resolved OPTIMADE backend {self.backend!r} to non-class object {resolved!r}")
        return resolved

    def resolve_view(self) -> type:
        """Import and return this binding's view class on demand."""

        resolved = resolve_callable(self.view)
        if not isinstance(resolved, type):
            raise TypeError(f"Resolved OPTIMADE view {self.view!r} to non-class object {resolved!r}")
        return resolved

    def resolve_property_decoder(self, definition_id: str) -> Callable[..., Any] | None:
        """Resolve one property decoder, or return ``None`` when it is unbound."""

        try:
            reference = self.property_decoders[definition_id]
        except KeyError:
            return None
        return resolve_callable(reference)


_optimade_entry_bindings: dict[str, OptimadeEntryBinding] = {}


def register_optimade_entry_binding(
    *,
    name: str,
    definition_id: str,
    backend: str,
    view: str,
    property_decoders: Mapping[str, str] | None = None,
    query_fields: tuple[str, ...] | None = None,
) -> None:
    """Register one lazy typed binding, selected only by exact definition IRI."""

    binding = OptimadeEntryBinding(
        name=name,
        definition_id=definition_id,
        backend=backend,
        view=view,
        property_decoders={} if property_decoders is None else property_decoders,
        query_fields=query_fields,
    )
    if definition_id in _optimade_entry_bindings:
        raise ValueError(f"OPTIMADE entry binding is already registered: {definition_id!r}")
    _optimade_entry_bindings[definition_id] = binding


def known_optimade_entry_bindings() -> tuple[str, ...]:
    """Return registered entry-type definition IRIs without resolving imports."""

    return tuple(sorted(_optimade_entry_bindings))


def optimade_entry_binding(definition_id: str) -> OptimadeEntryBinding | None:
    """Return the exact-IRI binding without importing its backend or view."""

    return _optimade_entry_bindings.get(definition_id)


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
