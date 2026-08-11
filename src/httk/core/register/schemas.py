"""Schema and definition resource registries."""

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
import json
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..property_definitions import EntryTypeDefinition, PropertyDefinition


_entry_type_definitions: dict[str, str] = {}
_property_definitions: dict[str, str] = {}


def register_entry_type_definition(*, definition_id: str, resource: str) -> None:
    """Register one resource for an entry-type definition IRI.

    :param definition_id: The entry-type definition IRI.
    :param resource: The package resource reference to load.
    :raises ValueError: If ``definition_id`` is already registered.
    """
    if definition_id in _entry_type_definitions:
        raise ValueError(f"entry-type definition is already registered: {definition_id!r}")
    _entry_type_definitions[definition_id] = resource


def known_entry_type_definitions() -> list[str]:
    """Return registered entry-type definition IRIs.

    :return: Registered entry-type definition identifiers.
    """
    return sorted(_entry_type_definitions)


def register_property_definition(*, definition_id: str, resource: str) -> None:
    """Register one resource for a property definition IRI.

    :param definition_id: The property definition IRI.
    :param resource: The package resource reference to load.
    :raises ValueError: If ``definition_id`` is already registered.
    """
    if definition_id in _property_definitions:
        raise ValueError(f"property definition is already registered: {definition_id!r}")
    _property_definitions[definition_id] = resource


def known_property_definitions() -> list[str]:
    """Return registered property definition IRIs.

    :return: Registered property definition identifiers.
    """
    return sorted(_property_definitions)


def _resource(resource: str) -> dict[str, Any]:
    package, separator, filename = resource.partition(":")
    if not separator or not package or not filename:
        raise ValueError(f"Invalid registry resource {resource!r}; expected 'package:filename.json'")
    return cast(dict[str, Any], json.loads(files(package).joinpath(filename).read_text(encoding="utf-8")))


@cache
def load_entry_type_definition(definition_id: str) -> "EntryTypeDefinition":
    """Load and verify a registered entry-type definition resource.

    :param definition_id: The registered entry-type definition IRI.
    :return: The loaded and validated entry-type definition.
    :raises ValueError: If the IRI is unregistered or disagrees with the document.
    """
    try:
        resource = _entry_type_definitions[definition_id]
    except KeyError as exc:
        known = ", ".join(known_entry_type_definitions()) or "(none)"
        raise ValueError(f"No entry-type definition registered for {definition_id!r}. Known: {known}") from exc
    from ..property_definitions import EntryTypeDefinition

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
    """Load and verify a registered property definition resource.

    :param definition_id: The registered property definition IRI.
    :return: The loaded and validated property definition.
    :raises ValueError: If the IRI is unregistered or disagrees with the document.
    """
    try:
        resource = _property_definitions[definition_id]
    except KeyError as exc:
        known = ", ".join(known_property_definitions()) or "(none)"
        raise ValueError(f"No property definition registered for {definition_id!r}. Known: {known}") from exc
    from ..property_definitions import PropertyDefinition

    document = _resource(resource)
    name = document.get("name", definition_id.rsplit("/", 1)[-1])
    definition = PropertyDefinition.from_optimade(name, document)
    document_id = definition.definition_id
    if document_id != definition_id:
        raise ValueError(
            f"Property definition registration IRI {definition_id!r} does not match document $id {document_id!r}"
        )
    return definition
