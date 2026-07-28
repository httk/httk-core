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

"""First-class OPTIMADE property and entry-type definitions.

An OPTIMADE *property definition* is a self-describing JSON document giving a
property's canonical identifier, type, unit, requirements, and human-readable
description. An *entry-type definition* bundles the property definitions of one
entry type (``structures``, ``references``, ...) together with the entry type's
own description.

This module models both as immutable Python objects:

- :class:`PropertyDefinition` wraps one full property-definition document. It can
  be built from a vendored OPTIMADE definition (:meth:`PropertyDefinition.from_optimade`)
  or generated from a compact description (:meth:`PropertyDefinition.from_simple`).
- :class:`EntryTypeDefinition` wraps an entry type's description and the ordered
  mapping of its property definitions, and can be
  :meth:`~EntryTypeDefinition.extended` with database-specific custom properties.

The vendored OPTIMADE standard definitions shipped with httk-core (the
``references``, ``files``, and ``calculations`` entry types) are loaded through
:func:`load_entry_type_definition` / :func:`standard_entry_type`. The
authoritative, supported copies are the JSON files checked in under
``httk/core/optimade_defs/`` (see the README there).

**On the "1.2" definition-format stamp:** :meth:`PropertyDefinition.from_simple`
generates only property-definition features that already exist in format
``"1.2"`` of the OPTIMADE property-definition schema, so every generated
definition is stamped ``x-optimade-definition.format == "1.2"``. The definition
*format* is versioned in lockstep with the OPTIMADE specification and is only
bumped when a definition actually uses features introduced by a newer format;
custom generated definitions therefore keep the ``"1.2"`` stamp even for
entry types (such as ``calculations``) whose specification version is newer.
"""

import copy
import json
import re
from collections.abc import Mapping
from functools import cache
from importlib.resources import files
from typing import Any, Self

PROPERTY_DEFINITION_META_SCHEMA = "https://schemas.optimade.org/meta/v1.2/optimade/property_definition.json"

_OPTIMADE_DEFS_BASE = "https://schemas.optimade.org/defs/v1.2/properties/optimade"
#: Where a property that httk defines *ad hoc* gets its synthesized ``$id``. Distinct
#: from the published-schema namespace at ``https://schemas.httk.org/defs/``: those are
#: definitions that really are served from there, whereas these are generated on the fly
#: by :meth:`PropertyDefinition.from_simple` and are not published anywhere.
_HTTK_DEFS_BASE = "https://schemas.httk.org/ad-hoc/defs/properties"

#: A valid definition prefix: a lower-case alphanumeric token wrapped in single
#: underscores (e.g. ``_httk_``, ``_omdb_``, ``_exmpl_``).
_DEFINITION_PREFIX_PATTERN = re.compile(r"^_[a-z0-9]+_$")

#: Registry of recognized database-specific property-name prefixes. Maps each
#: prefix to ``(id_base, source_label)``: ``id_base`` is the URL base under which
#: :meth:`PropertyDefinition.from_simple` synthesizes ``$id`` values for names
#: carrying the prefix, and ``source_label`` is the token used in the generated
#: ``x-optimade-definition.label``. See :func:`register_definition_prefix`.
_DEFINITION_PREFIXES: dict[str, tuple[str, str]] = {}


def register_definition_prefix(prefix: str, id_base: str) -> None:
    """Register a database-specific OPTIMADE property-name ``prefix``.

    A custom property served by a database MUST use such a prefix (see the
    OPTIMADE specification, "Database-Specific Properties"). Once registered, a
    property name carrying ``prefix`` gets its ``$id`` synthesized under
    ``id_base`` by :meth:`PropertyDefinition.from_simple`, and
    :meth:`EntryTypeDefinition.extended` accepts it as a custom property.

    ``prefix`` must be a lower-case alphanumeric token wrapped in single
    underscores (matching ``_[a-z0-9]+_``); anything else raises a clear
    :class:`ValueError`. Re-registering an existing prefix overwrites its base.
    """
    if not _DEFINITION_PREFIX_PATTERN.match(prefix):
        raise ValueError(
            "Invalid definition prefix "
            + repr(prefix)
            + "; a definition prefix must be a lower-case alphanumeric token wrapped in single "
            + "underscores, e.g. '_httk_'."
        )
    _DEFINITION_PREFIXES[prefix] = (id_base, prefix.strip("_"))


def known_definition_prefixes() -> tuple[str, ...]:
    """Return the registered database-specific property-name prefixes.

    The tuple reflects the current state of the prefix registry (see
    :func:`register_definition_prefix`); ``_httk_`` and ``_omdb_`` are
    pre-registered.
    """
    return tuple(_DEFINITION_PREFIXES)


def _matching_definition_prefix(name: str) -> str | None:
    """Return the registered prefix ``name`` starts with, or ``None``."""
    for prefix in _DEFINITION_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return None


# Pre-registered prefixes. Both historically resolve under the httk.org base
# with the "httk" source label (byte-identical to the previous behavior).
_DEFINITION_PREFIXES["_httk_"] = (_HTTK_DEFS_BASE, "httk")
_DEFINITION_PREFIXES["_omdb_"] = (_HTTK_DEFS_BASE, "httk")

_ANGSTROM_UNIT_DEFINITION = {
    "symbol": "angstrom",
    "title": "ångström",
    "description": "The ångström unit of length.",
    "standard": {
        "kind": "gnu units",
        "version": "3.15",
        "symbol": "angstrom",
    },
}

_JSON_TYPE_BY_OPTIMADE_TYPE = {
    "boolean": "boolean",
    "string": "string",
    "integer": "integer",
    "float": "number",
    "list": "array",
    "dictionary": "object",
    "timestamp": "string",
}


def _optimade_type(fulltype: str) -> str:
    if fulltype.startswith("list of "):
        return "list"
    if fulltype == "dict":
        return "dictionary"
    return fulltype


def _type_field(optimade_type: str, nullable: bool) -> list[str]:
    json_type = _JSON_TYPE_BY_OPTIMADE_TYPE[optimade_type]
    return [json_type, "null"] if nullable else [json_type]


def _inner_definition(fulltype: str, unit: str) -> dict[str, Any]:
    optimade_type = _optimade_type(fulltype)
    definition: dict[str, Any] = {
        "x-optimade-type": optimade_type,
        "x-optimade-unit": unit if optimade_type in ("integer", "float", "list") else "dimensionless",
        "type": _type_field(optimade_type, nullable=True),
    }
    if optimade_type == "list":
        definition["items"] = _inner_definition(fulltype[len("list of ") :], unit)
    if optimade_type == "timestamp":
        definition["format"] = "date-time"
    return definition


def _slice_object_definition() -> dict[str, Any]:
    """A modest definition of a "slice object" (start/stop/step)."""
    integer_field = {
        "x-optimade-type": "integer",
        "x-optimade-unit": "inapplicable",
        "type": ["integer", "null"],
    }
    return {
        "x-optimade-type": "dictionary",
        "x-optimade-unit": "inapplicable",
        "type": ["object", "null"],
        "properties": {
            "start": dict(integer_field),
            "stop": dict(integer_field),
            "step": dict(integer_field),
        },
    }


def _generated_metadata_definition(name: str) -> dict[str, Any]:
    """A standard ``x-optimade-metadata-definition`` describing ``list_axes``.

    Generated for properties that declare dimensions but do not carry an
    explicit metadata definition. It describes the ``list_axes`` metadata field
    used by the slicing protocol (see the OPTIMADE specification section
    "Slices of list properties").
    """
    return {
        "title": f"Metadata for the {name} field",
        "description": f"This field contains the per-entry metadata for the {name} field.",
        "x-optimade-type": "dictionary",
        "x-optimade-unit": "inapplicable",
        "type": ["object", "null"],
        "properties": {
            "list_axes": {
                "title": "List axes",
                "description": (
                    "Descriptive information related to the axes of this list property, including "
                    "sliceable axes. Each item, in order, represents a list axis as declared in the "
                    "property definition."
                ),
                "x-optimade-type": "list",
                "x-optimade-unit": "inapplicable",
                "type": ["array", "null"],
                "items": {
                    "x-optimade-type": "dictionary",
                    "x-optimade-unit": "inapplicable",
                    "type": ["object", "null"],
                    "properties": {
                        "dimension_name": {
                            "x-optimade-type": "string",
                            "x-optimade-unit": "inapplicable",
                            "type": ["string"],
                        },
                        "requested_slice": _slice_object_definition(),
                        "length": {
                            "x-optimade-type": "integer",
                            "x-optimade-unit": "inapplicable",
                            "type": ["integer", "null"],
                        },
                        "sliceable": {
                            "x-optimade-type": "boolean",
                            "x-optimade-unit": "inapplicable",
                            "type": ["boolean", "null"],
                        },
                        "available_slice": _slice_object_definition(),
                    },
                },
            },
        },
    }


class PropertyDefinition:
    """An immutable wrapper around one full OPTIMADE property definition.

    Instances are constructed from a vendored definition document
    (:meth:`from_optimade`) or generated from a compact description
    (:meth:`from_simple`). The wrapped document is always deep-copied on the way
    in and out, so an instance never shares mutable state with its inputs or its
    callers.
    """

    __slots__ = ("_name", "_payload")

    def __init__(self, name: str, payload: Mapping[str, Any]) -> None:
        # Private: prefer the classmethod constructors, which validate/generate.
        self._name = name
        self._payload: dict[str, Any] = copy.deepcopy(dict(payload))

    @classmethod
    def from_optimade(cls, name: str, definition: Mapping[str, Any]) -> Self:
        """Wrap a full vendored OPTIMADE property definition.

        ``definition`` must at least carry ``$id``, ``description``,
        ``x-optimade-type``, and ``type``; a clear :class:`ValueError` is raised
        otherwise. The document is deep-copied.
        """
        missing = [key for key in ("$id", "description", "x-optimade-type", "type") if key not in definition]
        if missing:
            raise ValueError(
                "Invalid OPTIMADE property definition for '"
                + name
                + "': missing required key(s): "
                + ", ".join(missing)
                + "."
            )
        return cls(name, definition)

    @classmethod
    def from_simple(
        cls,
        name: str,
        *,
        description: str,
        fulltype: str = "string",
        unit: str | None = None,
        dimensions: Mapping[str, Any] | None = None,
        dict_properties: Mapping[str, str] | None = None,
        metadata_definition: Mapping[str, Any] | None = None,
        required_response: bool = False,
        definition_id: str | None = None,
    ) -> Self:
        """Generate a property definition from a compact description.

        This mirrors the OPTIMADE property-definition generator: it emits the
        ``$schema`` meta-schema reference, a synthesized ``$id`` (under the base
        registered for a matching prefix via
        :func:`register_definition_prefix` — e.g. ``httk.org`` for ``_httk_`` /
        ``_omdb_`` — under ``schemas.optimade.org`` otherwise, unless
        ``definition_id`` overrides it), a title, the ``description``, the OPTIMADE type derived
        from ``fulltype`` (``"string"``, ``"integer"``, ``"float"``,
        ``"boolean"``, ``"timestamp"``, ``"dict"``, or ``"list of ..."``), the
        ``x-optimade-unit`` (with an ångström unit definition when
        ``unit == "angstrom"``), the ``x-optimade-definition`` stamp (format
        ``"1.2"``; see the module docstring), the JSON ``type`` with nullability
        derived from ``required_response``, ``items`` for lists, a ``date-time``
        format for timestamps, inner ``properties`` for dicts (from
        ``dict_properties``), ``x-optimade-dimensions`` from ``dimensions``, and
        an ``x-optimade-metadata-definition`` (explicit, or a generated
        ``list_axes`` definition when ``dimensions`` is given).

        The result is implementation-neutral: per-deployment ``sortable`` and
        ``response-default`` flags are layered on later via
        :meth:`with_implementation`.
        """
        optimade_type = _optimade_type(fulltype)
        resolved_unit = unit if unit is not None else "dimensionless"
        nullable = not required_response

        matched_prefix = _matching_definition_prefix(name)
        if definition_id is not None:
            resolved_id = definition_id
        elif matched_prefix is not None:
            resolved_id = f"{_DEFINITION_PREFIXES[matched_prefix][0]}/{name}"
        else:
            resolved_id = f"{_OPTIMADE_DEFS_BASE}/{name}"
        source = _DEFINITION_PREFIXES[matched_prefix][1] if matched_prefix is not None else "optimade"

        payload: dict[str, Any] = {
            "$schema": PROPERTY_DEFINITION_META_SCHEMA,
            "$id": resolved_id,
            "title": name.replace("_", " ").strip().capitalize(),
            "description": description,
            "x-optimade-type": optimade_type,
            "x-optimade-unit": resolved_unit,
            "x-optimade-definition": {
                "kind": "property",
                "format": "1.2",
                "name": name,
                "label": f"{name.lstrip('_')}_{source}",
            },
            "type": _type_field(optimade_type, nullable),
        }
        if optimade_type == "list":
            payload["items"] = _inner_definition(fulltype[len("list of ") :], resolved_unit)
        if optimade_type == "timestamp":
            payload["format"] = "date-time"
        if optimade_type == "dictionary":
            inner = dict_properties or {}
            payload["properties"] = {
                key: _inner_definition(inner_fulltype, "dimensionless") for key, inner_fulltype in inner.items()
            }
        if resolved_unit == "angstrom":
            payload["x-optimade-unit-definitions"] = [copy.deepcopy(_ANGSTROM_UNIT_DEFINITION)]

        if dimensions is not None:
            x_dimensions: dict[str, Any] = {"names": list(dimensions["names"]), "sizes": list(dimensions["sizes"])}
            if "compactable" in dimensions:
                x_dimensions["compactable"] = list(dimensions["compactable"])
            payload["x-optimade-dimensions"] = x_dimensions

        if metadata_definition is not None:
            payload["x-optimade-metadata-definition"] = copy.deepcopy(dict(metadata_definition))
        elif dimensions is not None:
            payload["x-optimade-metadata-definition"] = _generated_metadata_definition(name)

        return cls(name, payload)

    @property
    def name(self) -> str:
        return self._name

    @property
    def definition_id(self) -> str:
        return self._payload["$id"]

    @property
    def title(self) -> str | None:
        return self._payload.get("title")

    @property
    def description(self) -> str:
        return self._payload.get("description", "")

    @property
    def optimade_type(self) -> str:
        return self._payload["x-optimade-type"]

    @property
    def json_type(self) -> Any:
        return self._payload.get("type")

    @property
    def nullable(self) -> bool:
        json_type = self._payload.get("type")
        return isinstance(json_type, list) and "null" in json_type

    @property
    def unit(self) -> str | None:
        return self._payload.get("x-optimade-unit")

    @property
    def format_version(self) -> str | None:
        definition = self._payload.get("x-optimade-definition")
        if isinstance(definition, Mapping):
            return definition.get("format")
        return None

    @property
    def requirements(self) -> Mapping[str, Any]:
        return self._payload.get("x-optimade-requirements", {})

    @property
    def dimensions(self) -> Mapping[str, Any] | None:
        return self._payload.get("x-optimade-dimensions")

    @property
    def metadata_definition(self) -> Mapping[str, Any] | None:
        return self._payload.get("x-optimade-metadata-definition")

    def with_implementation(self, *, sortable: bool | None = None, response_default: bool | None = None) -> Self:
        """Return a copy carrying this deployment's implementation flags.

        Adds an ``x-optimade-implementation`` object with the ``sortable`` and
        ``response-default`` keys that are provided (a ``None`` argument leaves
        that key unset), and — when ``sortable`` is given — mirrors it in a
        top-level ``sortable`` field. The original instance is untouched.
        """
        payload = copy.deepcopy(self._payload)
        implementation: dict[str, Any] = dict(payload.get("x-optimade-implementation", {}))
        if sortable is not None:
            implementation["sortable"] = sortable
            payload["sortable"] = sortable
        if response_default is not None:
            implementation["response-default"] = response_default
        if implementation:
            payload["x-optimade-implementation"] = implementation
        return type(self)(self._name, payload)

    def as_optimade(self) -> dict[str, Any]:
        """Return a deep copy of the wrapped property-definition document."""
        return copy.deepcopy(self._payload)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PropertyDefinition):
            return NotImplemented
        return self._name == other._name and self._payload == other._payload

    def __repr__(self) -> str:
        return f"PropertyDefinition(name={self._name!r}, id={self.definition_id!r})"


class EntryTypeDefinition:
    """An immutable OPTIMADE entry-type definition.

    Bundles the entry type's ``name`` and ``description`` with an
    insertion-ordered mapping of :class:`PropertyDefinition` objects (one per
    described property). A standard definition typically describes more
    properties than any given deployment serves; the served subset is chosen
    separately (an :class:`~httk.core.EntryProvider` names it through its
    :meth:`~httk.core.EntryProvider.property_keys`).
    """

    __slots__ = ("_description", "_name", "_properties")

    def __init__(self, name: str, description: str, properties: Mapping[str, PropertyDefinition]) -> None:
        self._name = name
        self._description = description
        self._properties: dict[str, PropertyDefinition] = dict(properties)

    @classmethod
    def from_optimade(cls, name: str, entrytype: Mapping[str, Any]) -> Self:
        """Build an entry-type definition from a vendored OPTIMADE entry type.

        ``entrytype`` is the vendored document shape: a ``description`` string
        and a ``properties`` mapping of property name to full property
        definition. A clear :class:`ValueError` is raised when either is missing.
        """
        if "description" not in entrytype:
            raise ValueError("Invalid OPTIMADE entry-type definition for '" + name + "': missing 'description'.")
        if "properties" not in entrytype:
            raise ValueError("Invalid OPTIMADE entry-type definition for '" + name + "': missing 'properties'.")
        properties = {
            prop_name: PropertyDefinition.from_optimade(prop_name, prop_def)
            for prop_name, prop_def in entrytype["properties"].items()
        }
        return cls(name, entrytype["description"], properties)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def properties(self) -> Mapping[str, PropertyDefinition]:
        return dict(self._properties)

    def extended(self, extra: Mapping[str, PropertyDefinition], *, allow_unprefixed: bool = False) -> Self:
        """Return a copy with ``extra`` custom property definitions merged in.

        Each name in ``extra`` MUST be new (a collision with an existing
        property raises :class:`ValueError` naming it) and, unless
        ``allow_unprefixed`` is set, MUST carry a registered database-specific
        prefix (see :func:`register_definition_prefix` /
        :func:`known_definition_prefixes`); a custom property that does not is
        rejected with a :class:`ValueError` explaining the OPTIMADE prefix rule.
        """
        merged = dict(self._properties)
        recognized = known_definition_prefixes()
        for prop_name, definition in extra.items():
            if prop_name in merged:
                raise ValueError(
                    "Cannot extend entry type '"
                    + self._name
                    + "' with property '"
                    + prop_name
                    + "': a property with that name is already defined."
                )
            if not allow_unprefixed and not prop_name.startswith(recognized):
                raise ValueError(
                    "Custom property '"
                    + prop_name
                    + "' on entry type '"
                    + self._name
                    + "' must use a database-specific prefix ("
                    + ", ".join(recognized)
                    + "); OPTIMADE reserves unprefixed names for standard properties."
                )
            merged[prop_name] = definition
        return type(self)(self._name, self._description, merged)

    def as_optimade(self) -> dict[str, Any]:
        """Return the entry type as a vendored-shape OPTIMADE document."""
        return {
            "description": self._description,
            "properties": {name: prop.as_optimade() for name, prop in self._properties.items()},
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EntryTypeDefinition):
            return NotImplemented
        return (
            self._name == other._name
            and self._description == other._description
            and self._properties == other._properties
        )

    def __repr__(self) -> str:
        return f"EntryTypeDefinition(name={self._name!r}, properties={list(self._properties)!r})"


@cache
def load_entry_type_definition(package: str, name: str) -> EntryTypeDefinition:
    """Load a vendored OPTIMADE entry-type definition JSON from a package.

    Reads ``optimade_defs/<name>.json`` from ``package`` (via
    :mod:`importlib.resources`) and models it as an
    :class:`EntryTypeDefinition`. Results are cached per ``(package, name)``.
    """
    text = files(package).joinpath(f"optimade_defs/{name}.json").read_text(encoding="utf-8")
    document = json.loads(text)
    return EntryTypeDefinition.from_optimade(name, document)


_STANDARD_ENTRY_TYPES: tuple[str, ...] = ("references", "files", "calculations")


def standard_entry_type(name: str) -> EntryTypeDefinition:
    """Return one of httk-core's vendored standard OPTIMADE entry types.

    Supported names are ``"references"``, ``"files"``, and ``"calculations"``;
    an unknown name raises a :class:`ValueError` listing the known ones. The
    ``structures`` standard is vendored by *httk-atomistic*, not httk-core.
    """
    if name not in _STANDARD_ENTRY_TYPES:
        raise ValueError(
            "Unknown standard entry type: '"
            + name
            + "'. Known standard entry types in httk-core: "
            + ", ".join(_STANDARD_ENTRY_TYPES)
            + "."
        )
    return load_entry_type_definition("httk.core", name)
