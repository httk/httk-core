"""Entry-provider, entry-family, record, and binding registries."""

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
import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ._base import PluginRegistry, resolve_callable

entry_providers = PluginRegistry()


def register_entry_provider(*, name: str, factory: str) -> None:
    """Register an :class:`~httk.core.entry_provider.EntryProvider` factory under ``name``.

    ``factory`` is a lazy ``"module:callable"`` reference to a callable that
    constructs a provider (providers need data, so applications call the factory
    themselves; the registry only records how to reach it). This mirrors
    ``register_reader``.

    :param name: The provider registry name.
    :param factory: The lazy ``"module:callable"`` factory reference.
    """
    entry_providers.register(key=name, handler=factory, name=name)


def known_entry_providers() -> list[str]:
    """Return registered entry-provider names.

    :return: Registered provider names.
    """
    return entry_providers.keys()


_entry_records: dict[str, tuple[str, str | None, str | None]] = {}


def register_entry_record(
    *, name: str, record: str, family: str | None = None, definition_id: str | None = None
) -> None:
    """Register a lazy record-class reference and optional family and definition IRI.

    :param name: The record registry name.
    :param record: The lazy ``"module:class"`` record reference.
    :param family: The logical entry-family name, if any.
    :param definition_id: The record's definition IRI, if any.
    :raises ValueError: If validation fails or ``name`` is already registered.
    """
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
    """Return registered record names, optionally limited to a family.

    :param family: An entry-family name to filter by, or ``None`` for all records.
    :return: Matching record registry names.
    """
    return sorted(
        name
        for name, (_, registered_family, _) in _entry_records.items()
        if family is None or family == registered_family
    )


def entry_record_info(name: str) -> tuple[str, str | None, str | None]:
    """Return record, family, and definition metadata without importing the record class.

    :param name: The registered record name.
    :return: The lazy record reference and optional family and definition IRI.
    :raises ValueError: If ``name`` is not registered.
    """
    try:
        return _entry_records[name]
    except KeyError as exc:
        known = ", ".join(known_entry_records()) or "(none)"
        raise ValueError(f"No entry record registered for {name!r}. Known: {known}") from exc


def resolve_entry_record(name: str) -> type:
    """Import and return a registered record class.

    :param name: The registered record name.
    :return: The resolved frozen dataclass record class.
    :raises ValueError: If ``name`` is not registered.
    :raises TypeError: If the reference does not resolve to a frozen dataclass.
    """
    resolved = resolve_callable(entry_record_info(name)[0])
    if not isinstance(resolved, type):
        raise TypeError(f"Resolved entry record {name!r} to non-class object {resolved!r}")
    params = getattr(resolved, "__dataclass_params__", None)
    if not dataclasses.is_dataclass(resolved) or params is None or not params.frozen:
        raise TypeError(f"Resolved entry record {name!r} to a non-frozen dataclass {resolved!r}")
    return resolved


_entry_families: dict[str, tuple[str, str | None]] = {}


def register_entry_family(*, name: str, family: str, definition_id: str | None = None) -> None:
    """Register a lazy entry-family class reference without importing it.

    :param name: The entry-family registry name.
    :param family: The lazy ``"module:class"`` family reference.
    :param definition_id: The family's definition IRI, if any.
    :raises ValueError: If validation fails or ``name`` is already registered.
    """
    _validate_nonempty_optimade_string(name, label="entry family name")
    _validate_optimade_reference(family, label="entry family")
    if definition_id is not None:
        _validate_nonempty_optimade_string(definition_id, label="definition_id")
    if name in _entry_families:
        raise ValueError(f"entry family is already registered: {name!r}")
    _entry_families[name] = (family, definition_id)


def known_entry_families() -> list[str]:
    """Return registered entry-family names.

    :return: Registered entry-family names.
    """
    return sorted(_entry_families)


def entry_family_info(name: str) -> tuple[str, str | None]:
    """Return entry-family metadata without importing its class.

    :param name: The registered entry-family name.
    :return: The lazy family reference and optional definition IRI.
    :raises ValueError: If ``name`` is not registered.
    """
    try:
        return _entry_families[name]
    except KeyError as exc:
        known = ", ".join(known_entry_families()) or "(none)"
        raise ValueError(f"No entry family registered for {name!r}. Known: {known}") from exc


def resolve_entry_family(name: str) -> type:
    """Import and return a registered entry-family class.

    :param name: The registered entry-family name.
    :return: The resolved entry-family class.
    :raises ValueError: If ``name`` is not registered.
    :raises TypeError: If the reference does not resolve to a class.
    """
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
    """Describe lazy typed handling for one exact entry-type definition IRI.

    :param name: The binding registry name.
    :param definition_id: The exact entry-type definition IRI selected by the binding.
    :param backend: The lazy backend class reference.
    :param view: The lazy view class reference.
    :param property_decoders: Property definition IRIs mapped to lazy decoder references.
    :param query_fields: Property definition IRIs supported for querying, if restricted.
    """

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
        """Import and return this binding's backend class on demand.

        :return: The resolved backend class.
        :raises TypeError: If the lazy reference does not resolve to a class.
        """

        resolved = resolve_callable(self.backend)
        if not isinstance(resolved, type):
            raise TypeError(f"Resolved OPTIMADE backend {self.backend!r} to non-class object {resolved!r}")
        return resolved

    def resolve_view(self) -> type:
        """Import and return this binding's view class on demand.

        :return: The resolved view class.
        :raises TypeError: If the lazy reference does not resolve to a class.
        """

        resolved = resolve_callable(self.view)
        if not isinstance(resolved, type):
            raise TypeError(f"Resolved OPTIMADE view {self.view!r} to non-class object {resolved!r}")
        return resolved

    def resolve_property_decoder(self, definition_id: str) -> Callable[..., Any] | None:
        """Resolve one property decoder, or return ``None`` when it is unbound.

        :param definition_id: The property definition IRI to resolve.
        :return: The decoder callable, or ``None`` when no decoder is registered.
        """

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
    """Register one lazy typed binding, selected only by exact definition IRI.

    :param name: The binding registry name.
    :param definition_id: The exact entry-type definition IRI selected by the binding.
    :param backend: The lazy backend class reference.
    :param view: The lazy view class reference.
    :param property_decoders: Property definition IRIs mapped to lazy decoder references.
    :param query_fields: Property definition IRIs supported for querying, if restricted.
    :raises ValueError: If the definition IRI is already registered or input is invalid.
    """

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
    """Return registered entry-type definition IRIs without resolving imports.

    :return: Exact definition IRIs with registered bindings.
    """

    return tuple(sorted(_optimade_entry_bindings))


def optimade_entry_binding(definition_id: str) -> OptimadeEntryBinding | None:
    """Return the exact-IRI binding without importing its backend or view.

    :param definition_id: The exact entry-type definition IRI to look up.
    :return: The binding, or ``None`` if no exact match is registered.
    """

    return _optimade_entry_bindings.get(definition_id)
