"""Structural compatibility checks for record dataclasses and entry schemas.

This is a *structural compatibility* check: it compares property/field names,
nullability, and shallow Python type shape.  It deliberately does not check
units, requirements or sortable flags, dictionary value schemas, nested
required keys, enums or patterns, or cross-field constraints.  A passing check
therefore does not mean that two models are semantically equivalent.
"""

import types
from collections.abc import Collection, Mapping
from dataclasses import fields
from datetime import datetime
from typing import Annotated, Any, TypeAliasType, Union, get_args, get_origin, get_type_hints

from .property_definitions import EntryTypeDefinition, PropertyDefinition
from .storage_markers import Shape
from .vectors import FracVector

__all__ = ["check_record_matches_definition"]

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "float": float,
    "timestamp": datetime,
}
_UNION_ORIGINS = (Union, types.UnionType)


def _unwrap(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    metadata: list[Any] = []
    while True:
        if isinstance(annotation, TypeAliasType):
            annotation = annotation.__value__
        elif get_origin(annotation) is Annotated:
            args = get_args(annotation)
            annotation = args[0]
            metadata.extend(args[1:])
        else:
            break
    return annotation, tuple(metadata)


def _is_nullable(annotation: Any) -> bool:
    annotation, _ = _unwrap(annotation)
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        return any(arg is type(None) or _is_nullable(arg) for arg in get_args(annotation))
    return False


def _without_none(annotation: Any) -> Any:
    annotation, _ = _unwrap(annotation)
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        remaining = tuple(arg for arg in get_args(annotation) if arg is not type(None))
        if len(remaining) == 1:
            return _without_none(remaining[0])
        return annotation
    return annotation


def _shape_marker(annotation: Any) -> Shape | None:
    annotation, metadata = _unwrap(annotation)
    for marker in metadata:
        if isinstance(marker, Shape):
            return marker
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        for arg in get_args(annotation):
            if arg is not type(None):
                marker = _shape_marker(arg)
                if marker is not None:
                    return marker
    return None


def _definition_shape(definition: PropertyDefinition) -> Any:
    document = definition.as_optimade()

    def shape(node: Mapping[str, Any]) -> Any:
        kind = node["x-optimade-type"]
        if kind == "list":
            return ("list", shape(node["items"]))
        return kind

    return shape(document)


def _is_mapping(annotation: Any) -> bool:
    annotation, _ = _unwrap(annotation)
    origin = get_origin(annotation)
    return annotation in (Mapping, dict) or origin in (Mapping, dict)


def _is_list(annotation: Any, expected: Any) -> bool:
    annotation, _ = _unwrap(annotation)
    origin = get_origin(annotation)
    if annotation not in (list, tuple) and origin not in (list, tuple):
        return False
    args = get_args(annotation)
    if not args:
        return False
    if origin is tuple:
        if len(args) != 2 or args[1] is not Ellipsis:
            return False
        return _matches_shape(args[0], expected)
    return len(args) == 1 and _matches_shape(args[0], expected)


def _matches_shape(annotation: Any, expected: Any) -> bool:
    annotation = _without_none(annotation)
    annotation, _ = _unwrap(annotation)
    if isinstance(expected, tuple):
        return expected[0] == "list" and _is_list(annotation, expected[1])
    if expected == "dictionary":
        return _is_mapping(annotation)
    if expected == "list":
        return _is_list(annotation, "string")
    expected_python = _JSON_TYPES.get(expected)
    return expected_python is not None and annotation is expected_python


def _shape_matches_dimensions(marker: Shape, definition: PropertyDefinition) -> bool:
    dimensions = definition.dimensions
    if dimensions is None:
        return True
    sizes = dimensions.get("sizes", ())
    if len(sizes) != 2:
        return False
    for actual, expected in zip((marker.rows, marker.cols), sizes):
        if expected is None or expected == 0:
            if actual != 0:
                return False
        elif actual != expected:
            return False
    return True


def _type_matches(annotation: Any, definition: PropertyDefinition) -> bool:
    expected = _definition_shape(definition)
    marker = _shape_marker(annotation)
    base = _without_none(annotation)
    base, _ = _unwrap(base)
    if base is FracVector:
        return expected == ("list", ("list", "float")) and marker is not None
    return _matches_shape(base, expected)


def check_record_matches_definition(
    record: type,
    definition: EntryTypeDefinition,
    *,
    property_keys: Mapping[str, str] | None = None,
    internal_fields: Collection[str] = (),
    ignore_properties: Collection[str] = ("id", "type"),
) -> list[str]:
    """Return structural mismatches between a dataclass and an entry definition.

    ``property_keys`` maps dataclass field names to served property names; it is
    the inverse of :meth:`~httk.core.entry_provider.EntryProvider.property_keys`, which maps served
    property names to record keys.  An omitted mapping uses identity for every
    field.  ``internal_fields`` are skipped on the dataclass side, and
    ``ignore_properties`` are skipped on the definition side.  Messages are
    sorted for stable output.
    """
    hints = get_type_hints(record, include_extras=True)
    record_fields = {field.name: field for field in fields(record)}
    internal = set(internal_fields)
    ignored = set(ignore_properties)
    keys = property_keys or {}
    properties = definition.properties
    messages: list[str] = []
    mapped: dict[str, str] = {}

    for field_name in record_fields:
        if field_name in internal:
            continue
        property_name = keys.get(field_name, field_name)
        mapped[field_name] = property_name
        if property_name not in properties:
            messages.append(
                f"field '{field_name}' maps to property '{property_name}', but that property is missing "
                "from the definition (field -> property)"
            )

    for property_name in properties:
        if property_name in ignored:
            continue
        field_names = [field_name for field_name, name in mapped.items() if name == property_name]
        if not field_names:
            messages.append(f"property '{property_name}' has no corresponding field in the record (property -> field)")
            continue
        for field_name in field_names:
            annotation = hints[field_name]
            field_nullable = _is_nullable(annotation)
            property_nullable = properties[property_name].nullable
            if field_nullable != property_nullable:
                if field_nullable:
                    messages.append(
                        f"field '{field_name}' for property '{property_name}' is nullable, but the property "
                        "is non-nullable (field -> property nullability)"
                    )
                else:
                    messages.append(
                        f"field '{field_name}' for property '{property_name}' is non-nullable, but the property "
                        "is nullable (property -> field nullability)"
                    )
            if not _type_matches(annotation, properties[property_name]):
                messages.append(
                    f"field '{field_name}' annotation {annotation!r} does not match property "
                    f"'{property_name}' type {properties[property_name].optimade_type!r} "
                    "(field -> property type shape)"
                )
            marker = _shape_marker(annotation)
            if (
                marker is not None
                and _without_none(annotation) is FracVector
                and not _shape_matches_dimensions(marker, properties[property_name])
            ):
                messages.append(
                    f"field '{field_name}' Shape({marker.rows}, {marker.cols}) does not match property "
                    f"'{property_name}' dimensions {properties[property_name].dimensions!r} "
                    "(field -> property dimensions)"
                )

    return sorted(messages)
