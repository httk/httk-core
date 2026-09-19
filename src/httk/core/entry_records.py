"""Declarative frozen records with explicit OPTIMADE property metadata."""

import datetime
import hashlib
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields, replace
from inspect import get_annotations
from typing import Annotated, Any, ClassVar, Union, dataclass_transform, get_args, get_origin, get_type_hints

from .data_records import RECORDS_DEFINITION_ID
from .property_definitions import EntryTypeDefinition, PropertyDefinition, known_definition_prefixes
from .register.schemas import load_entry_type_definition
from .storage import IdentitySkip, Indexed, Skip, StorageInfo, StoredPropertyProjection, Unique
from .storage.stored_properties import QueryContext, QueryExpression

__all__ = ["DataEntryRecord", "EntryRecord", "Property", "entry_record"]


@dataclass(frozen=True, kw_only=True)
class EntryRecord:
    """Common metadata for application-defined served records.

    Subclasses declare their entry family's ``type`` and ``definition_id`` and
    use :func:`entry_record` to become concrete frozen records. Metadata fields
    are keyword-only and excluded from equality and content identity.

    :param id: Public lineage identifier, assigned by the store when omitted.
    :param immutable_id: Revision identifier, assigned by the store when omitted.
    :param last_modified: Optional timezone-aware source modification time.
    :raises ValueError: If an identifier is empty or a timestamp lacks a timezone.
    """

    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    type: ClassVar[str]
    definition_id: ClassVar[str]
    __httk_entry_name__: ClassVar[str]
    __httk_property_definitions__: ClassVar[Mapping[str, PropertyDefinition]]
    __httk_stored_properties__: ClassVar[Mapping[str, StoredPropertyProjection]]
    __httk_storage__: ClassVar[StorageInfo]

    def __post_init__(self) -> None:
        """Validate explicitly supplied entry metadata."""
        for name in ("id", "immutable_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value or value != value.strip()):
                raise ValueError(f"{name} must be a nonempty string without surrounding whitespace or None")
        if self.last_modified is not None and (
            not isinstance(self.last_modified, datetime.datetime) or self.last_modified.utcoffset() is None
        ):
            raise ValueError("last_modified must be a timezone-aware datetime or None")

    @classmethod
    def entry_type_definition(cls) -> EntryTypeDefinition:
        """Return this concrete record's extended entry-family definition.

        :return: The base family definition extended with declared properties.
        :raises TypeError: If the class was not decorated with :func:`entry_record`.
        :raises ValueError: If a standard property definition is replaced.
        """
        if "__httk_property_definitions__" not in vars(cls):
            raise TypeError(f"{cls.__name__} must be decorated with entry_record")
        base = load_entry_type_definition(cls.definition_id)
        extra = {}
        for name, definition in cls.__httk_property_definitions__.items():
            if name in base.properties:
                if definition.as_optimade() != base.properties[name].as_optimade():
                    raise ValueError(f"{name}: a standard property definition cannot be replaced")
            else:
                extra[name] = definition
        return base.extended(extra)


class DataEntryRecord(EntryRecord):
    """Base for typed application records served at ``_httk_records``.

    No scientific fields are prescribed. This does not replace the existing
    :class:`~httk.core.data_records.DataRecord` single-property value model.
    """

    type: ClassVar[str] = "records"
    definition_id: ClassVar[str] = RECORDS_DEFINITION_ID


@dataclass(frozen=True, kw_only=True)
class Property:
    """Declare a served scalar field through ``Annotated`` metadata.

    The Python annotation supplies the type (``str``, ``int``, ``float``, or
    ``bool``, optionally nullable). Only marked fields become served attributes.
    Use an existing :class:`~httk.core.property_definitions.PropertyDefinition`
    as the annotation metadata instead when a curated definition exists.

    :param description: Scientific meaning of the field, including normalization.
    :param unit: Property unit; omitted means dimensionless.
    :param name: Served name; omitted uses ``_httk_custom_<field>``.
    """

    description: str
    unit: str | None = None
    name: str | None = None


def _scalar_type(annotation: Any) -> tuple[str, bool]:
    """Resolve the exact scalar types supported by direct field mappings."""
    nullable = False
    if get_origin(annotation) in (types.UnionType, Union):
        args = get_args(annotation)
        if len(args) == 2 and type(None) in args:
            annotation = next(arg for arg in args if arg is not type(None))
            nullable = True
    names = {str: "string", int: "integer", float: "float", bool: "boolean"}
    if annotation not in names:
        raise TypeError(
            "Property fields require str, int, float, or bool (optionally | None); use explicit projections otherwise"
        )
    return names[annotation], nullable


def _projection(field_name: str) -> StoredPropertyProjection:
    """Build independent direct-field callbacks for one scalar property."""

    def query(context: QueryContext, operator: str, value: object) -> QueryExpression:
        return context.compare(context.field(field_name), operator, context.constant(value))

    return StoredPropertyProjection(
        response=lambda record: getattr(record, field_name),
        query=query,
        sort=lambda context: context.field(field_name),
    )


@dataclass_transform(frozen_default=True)
def entry_record[T: EntryRecord](name: str) -> Callable[[type[T]], type[T]]:
    """Declare a frozen served record with a stable, explicit identity.

    This decorator does not register global plugins. Pass the resulting class
    explicitly to the store on creation and reopening. Referenced records remain
    ordinary dataclass fields. Property mappings are compiled for each concrete
    class; subclasses must opt in with their own decoration and identity.

    :param name: Stable logical identity, independent of the Python module/name.
    :return: A decorator that creates a frozen dataclass and its served mappings.
    :raises TypeError: If the class, field type, or declaration is unsupported.
    :raises ValueError: If identities, property names, or definitions conflict.
    """
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("entry_record requires a nonempty stable name without surrounding whitespace")

    def decorate(cls: type[T]) -> type[T]:
        if not issubclass(cls, EntryRecord):
            raise TypeError("entry_record requires an EntryRecord subclass")
        if "__dataclass_fields__" in vars(cls):
            raise TypeError("entry_record replaces @dataclass; do not apply both decorators")
        # Resolve this class's own annotations, including deferred ones on Python 3.14.
        if any(key in get_annotations(cls) for key in ("id", "immutable_id", "last_modified")):
            raise TypeError("entry_record metadata fields must retain the EntryRecord declarations")
        if "__httk_stored_properties__" in vars(cls) or "__httk_property_definitions__" in vars(cls):
            raise TypeError(
                "entry_record generates property declarations; use an explicit record for custom projections"
            )
        if not isinstance(getattr(cls, "definition_id", None), str) or not isinstance(getattr(cls, "type", None), str):
            raise TypeError("EntryRecord subclasses must declare type and definition_id")
        base = load_entry_type_definition(cls.definition_id)
        if cls.type != base.name:
            raise ValueError("record type must match its entry-family definition")
        storage = vars(cls).get("__httk_storage__", StorageInfo())
        if not isinstance(storage, StorageInfo):
            raise TypeError("__httk_storage__ must be StorageInfo")
        if storage.identity_name not in (None, name):
            raise ValueError("StorageInfo.identity_name conflicts with the entry_record name")
        cls = dataclass(frozen=True)(cls)
        hints = get_type_hints(cls, localns={cls.__name__: cls}, include_extras=True)
        for field_name, hint in hints.items():
            if get_origin(hint) is ClassVar:
                inner = get_args(hint)[0]
                if get_origin(inner) is Annotated and any(
                    isinstance(marker, (Property, PropertyDefinition)) for marker in get_args(inner)[1:]
                ):
                    raise TypeError(f"{field_name}: a served property must be an instance field, not ClassVar")
        definitions: dict[str, PropertyDefinition] = {}
        projections: dict[str, StoredPropertyProjection] = {}
        for item in fields(cls):
            hint = hints[item.name]
            if get_origin(hint) is not Annotated:
                continue
            annotation, *metadata = get_args(hint)
            markers = [marker for marker in metadata if isinstance(marker, (Property, PropertyDefinition))]
            if not markers:
                continue
            if len(markers) != 1:
                raise ValueError(f"{item.name} must have exactly one property declaration")
            if any(isinstance(marker, IdentitySkip) for marker in metadata):
                raise ValueError(f"{item.name}: identity metadata cannot declare a scientific property")
            if any(isinstance(marker, Skip) for marker in metadata):
                raise ValueError(f"{item.name}: a skipped field cannot declare a served property")
            fulltype, nullable = _scalar_type(annotation)
            marker = markers[0]
            if isinstance(marker, Property):
                if not isinstance(marker.description, str) or not marker.description.strip():
                    raise ValueError(f"{item.name}: Property requires a nonempty description")
                if marker.name is not None and (not isinstance(marker.name, str) or not marker.name.isidentifier()):
                    raise ValueError(f"{item.name}: Property.name must be a nonempty identifier")
                definition = PropertyDefinition.from_simple(
                    marker.name or f"_httk_custom_{item.name}",
                    description=marker.description,
                    fulltype=fulltype,
                    unit=marker.unit,
                )
            else:
                definition = marker
                if definition.optimade_type != fulltype or (nullable and not definition.nullable):
                    raise ValueError(f"{item.name}: property definition conflicts with the Python field type")
            served_name = definition.name
            if served_name not in base.properties and not any(
                served_name.startswith(prefix) for prefix in known_definition_prefixes()
            ):
                raise ValueError(f"{served_name}: custom property names require a registered provider prefix")
            if served_name in definitions or served_name in ("id", "type", "immutable_id", "last_modified"):
                raise ValueError(f"duplicate or reserved served property name {served_name!r}")
            definitions[served_name] = definition
            projections[served_name] = _projection(item.name)
        cls.__httk_entry_name__ = name
        cls.__httk_storage__ = replace(
            storage,
            identity_name=name,
            storage_name=storage.storage_name or "entry_" + hashlib.sha256(name.encode()).hexdigest()[:24],
        )
        cls.__httk_property_definitions__ = definitions
        cls.__httk_stored_properties__ = projections
        # Validate extension compatibility at definition time, not the first request.
        cls.entry_type_definition()
        return cls

    return decorate
