"""Domain-neutral declarations for serving durable entry records.

Domain packages can attach :class:`StoredEntryProjection` to a frozen storable
dataclass without depending on a database implementation.  A storage consumer
uses the declaration to expose standard entry-property names while continuing
to store and query ordinary dataclass fields.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable
from urllib.parse import urlsplit

from .storage_markers import stored_property

__all__ = [
    "STORED_ENTRY_PROJECTION_ATTRIBUTE",
    "StoredEntryProjection",
    "StoredEntryValue",
    "stored_entry_projection",
]

STORED_ENTRY_PROJECTION_ATTRIBUTE: Final = "__httk_entry_projection__"
"""Class attribute holding a :class:`StoredEntryProjection`."""


@runtime_checkable
class StoredEntryValue(Protocol):
    """A typed durable nested value with an explicit served-value projection."""

    def to_stored_entry_value(self) -> Any:
        """Return the domain-neutral value recursively serialized by a storage consumer."""
        ...


@dataclass(frozen=True, slots=True)
class StoredEntryProjection:
    """Map standard served properties onto fields of one stored record class.

    ``property_fields`` covers every property the record can serve, including
    ``id``. ``type`` is the constant :attr:`entry_type` and therefore has no
    backing field. ``filterable`` names the subset whose backing fields a
    storage engine may translate directly into native queries. Other mapped
    fields remain typed, durable, and servable but are intentionally not
    promised as storage-native filter targets. ``obsolete_storage_names`` lets
    the declaring domain name incompatible prior root tables so a consumer can
    issue a rebuild-required error without knowing that domain.
    """

    entry_type: str
    definition_id: str
    property_fields: Mapping[str, str]
    filterable: frozenset[str] = frozenset()
    obsolete_storage_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entry_type, str) or not self.entry_type or self.entry_type != self.entry_type.strip():
            raise ValueError("StoredEntryProjection entry_type must be a non-empty stripped string")
        if (
            not isinstance(self.definition_id, str)
            or not self.definition_id
            or self.definition_id != self.definition_id.strip()
            or not urlsplit(self.definition_id).scheme
        ):
            raise ValueError("StoredEntryProjection definition_id must be an absolute IRI")
        mapped = dict(self.property_fields)
        if "type" in mapped:
            raise ValueError("StoredEntryProjection 'type' is constant and must not name a record field")
        if "id" not in mapped:
            raise ValueError("StoredEntryProjection property_fields must map the standard 'id' property")
        for name, field_name in mapped.items():
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(field_name, str)
                or not field_name.isidentifier()
            ):
                raise ValueError("StoredEntryProjection property and field names must be non-empty identifiers")
        filterable = frozenset(self.filterable)
        unknown = filterable - set(mapped)
        if unknown:
            raise ValueError(
                "StoredEntryProjection filterable properties must be mapped: " + ", ".join(sorted(unknown))
            )
        object.__setattr__(self, "property_fields", MappingProxyType(mapped))
        object.__setattr__(self, "filterable", filterable)
        obsolete = tuple(self.obsolete_storage_names)
        if any(not isinstance(name, str) or not name or not name.isidentifier() for name in obsolete):
            raise ValueError("StoredEntryProjection obsolete storage names must be identifiers")
        if len(obsolete) != len(set(obsolete)):
            raise ValueError("StoredEntryProjection obsolete storage names must be unique")
        object.__setattr__(self, "obsolete_storage_names", obsolete)


def stored_entry_projection(cls: type[Any]) -> StoredEntryProjection | None:
    """Return and validate the stored-entry projection attached to ``cls``.

    ``None`` means the class is an ordinary storable dataclass. A malformed
    declaration fails at the consumption boundary with a precise error instead
    of silently falling back to database-specific property names.
    """

    value = getattr(cls, STORED_ENTRY_PROJECTION_ATTRIBUTE, None)
    if value is None:
        return None
    if not isinstance(value, StoredEntryProjection):
        raise TypeError(f"{cls.__name__}.{STORED_ENTRY_PROJECTION_ATTRIBUTE} must be a StoredEntryProjection")
    if not is_dataclass(cls):
        raise TypeError(f"stored-entry projection target {cls.__name__} must be a dataclass")
    known = {field.name for field in fields(cls)}
    for base in cls.__mro__:
        known.update(name for name, member in vars(base).items() if isinstance(member, stored_property))
    missing = sorted(set(value.property_fields.values()) - known)
    if missing:
        raise ValueError(
            f"stored-entry projection for {cls.__name__} names unknown dataclass fields: {', '.join(missing)}"
        )
    return value
