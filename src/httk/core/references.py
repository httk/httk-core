"""Stdlib-only storage records for OPTIMADE ``references`` entries.

``ReferenceRecord`` is the storable backing of the OPTIMADE ``references``
entry type. References are content-deduplicated: identity is every
bibliographic field, so the same reference cited from many entries is one
entry. The generated ``authors``/``editors`` mappings are not SQL-storable, so
the record stores them as :class:`PersonRecord` children and serves them back
in the OPTIMADE ``{"name", "firstname", "lastname"}`` dictionary shape.
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Annotated, Any, ClassVar, Self, cast

from .entry_types import Reference
from .storage import (
    IdentitySkip,
    Indexed,
    QueryContext,
    QueryExpression,
    StorageInfo,
    StoredPropertyProjection,
    Unique,
)

REFERENCES_DEFINITION_ID = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references"


@dataclass(frozen=True)
class PersonRecord:
    """Store one author or editor of a :class:`ReferenceRecord`.

    :param name: The full name of the person.
    :param firstname: The first name, if given separately.
    :param lastname: The last name, if given separately.
    :raises TypeError: If a name part is not a string (``firstname``/``lastname`` may be None).
    :raises ValueError: If ``name`` is empty.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_reference_person",
        identity_name="core_reference_person",
    )

    name: str
    firstname: str | None = None
    lastname: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f"PersonRecord name must be a str, got {type(self.name).__name__}")
        if not self.name:
            raise ValueError("PersonRecord name must be a nonempty string")
        for name in ("firstname", "lastname"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"PersonRecord {name} must be a str or None, got {type(value).__name__}")


def _persons(field_name: str, values: object) -> tuple[PersonRecord, ...] | None:
    """Coerce an ``authors``/``editors`` value into person records.

    :param field_name: The field being coerced, for error messages.
    :param values: None, or a tuple or list of person records or OPTIMADE person mappings.
    :return: The person records, or None when ``values`` is None.
    :raises TypeError: If ``values`` or one of its items has the wrong type.
    :raises ValueError: If a mapping has unknown keys.
    """
    if values is None:
        return None
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"ReferenceRecord {field_name} must be a tuple or list of persons, or None")
    persons: list[PersonRecord] = []
    for value in cast(tuple[object, ...], values):
        if isinstance(value, PersonRecord):
            persons.append(value)
        elif isinstance(value, Mapping):
            unknown = sorted(set(cast(Mapping[str, Any], value)) - {"name", "firstname", "lastname"})
            if unknown:
                raise ValueError(
                    f"ReferenceRecord {field_name} item has unknown key(s): {', '.join(map(str, unknown))}"
                )
            persons.append(PersonRecord(**cast(Mapping[str, Any], value)))
        else:
            raise TypeError(
                f"ReferenceRecord {field_name} items must be PersonRecord or mappings, got {type(value).__name__}"
            )
    return tuple(persons)


_REFERENCE_PERSON_FIELDS = ("authors", "editors")
_REFERENCE_NONSTRING_FIELDS = ("last_modified", *_REFERENCE_PERSON_FIELDS)


@dataclass(frozen=True)
class ReferenceRecord(Reference):
    """Store one OPTIMADE ``references`` entry with content identity.

    A reference record is identified by its bibliographic content: every field
    except the store-minted ``id``/``immutable_id`` and ``last_modified``.
    ``authors`` and ``editors`` accept :class:`PersonRecord` values or OPTIMADE
    person mappings (``name`` with optional ``firstname``/``lastname``), which
    are coerced to :class:`PersonRecord`.

    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :param address: The publisher or institution address.
    :param annote: Additional notes on the reference.
    :param booktitle: The title of a book being cited.
    :param chapter: The chapter, section, or similar part number.
    :param crossref: The database key of a cross-referenced entry.
    :param edition: The edition of a book.
    :param howpublished: The method of publication.
    :param institution: The sponsoring institution of a technical report.
    :param journal: The journal name.
    :param key: The alphabetizing and cross-referencing label.
    :param month: The three-letter month abbreviation.
    :param note: Additional information about the reference.
    :param number: The journal, report, or series number.
    :param organization: The conference or manual sponsoring organization.
    :param pages: The page number(s).
    :param publisher: The publisher name.
    :param school: The school where a thesis was written.
    :param series: The series name.
    :param title: The title of the work.
    :param volume: The volume number.
    :param year: The year of publication, as a string.
    :param bib_type: The BibTeX entry type.
    :param authors: The authors, as person records or OPTIMADE person mappings.
    :param editors: The editors, as person records or OPTIMADE person mappings.
    :param doi: The DOI of the referenced object.
    :param url: The URL of the referenced object.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :raises TypeError: If a scalar field is neither a string nor None, or an author/editor has the wrong type.
    :raises ValueError: If an author/editor mapping has unknown keys or an empty ``name``.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_reference",
        identity_name="core_reference",
        indexes=(("doi",), ("title",)),
    )

    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    # Stored person children replace the generated, non-storable ``Mapping`` items.
    authors: tuple[PersonRecord, ...] | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]
    editors: tuple[PersonRecord, ...] | None = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        for item in fields(self):
            if item.name in _REFERENCE_NONSTRING_FIELDS:
                continue
            value = getattr(self, item.name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"ReferenceRecord {item.name} must be a str or None, got {type(value).__name__}")
        for name in _REFERENCE_PERSON_FIELDS:
            object.__setattr__(self, name, _persons(name, getattr(self, name)))

    @property
    def type(self) -> str:
        """Return the served entry type name."""
        return "references"


class ReferenceEntry:
    """Logical entry family for served :class:`ReferenceRecord` records.

    This family is not itself storable; store a ``ReferenceRecord`` directly.
    """

    type = "references"
    definition_id = REFERENCES_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("ReferenceEntry is a logical entry family; store a ReferenceRecord directly")


def _served_persons(field_name: str) -> StoredPropertyProjection:
    """Return a response-only projection serving ``authors``/``editors`` as OPTIMADE person dictionaries.

    :param field_name: ``"authors"`` or ``"editors"``.
    :return: A projection rendering each person as ``name`` plus its non-None name parts.
    """

    def response(served: object) -> list[dict[str, str]] | None:
        persons = cast(tuple[PersonRecord, ...] | None, getattr(served, field_name))
        if persons is None:
            return None
        return [
            {key: value for key in ("name", "firstname", "lastname") if (value := getattr(person, key)) is not None}
            for person in persons
        ]

    return StoredPropertyProjection(response=response)


def _served_string(field_name: str) -> StoredPropertyProjection:
    """Return a filterable, sortable projection serving one scalar string ``ReferenceRecord`` field.

    :param field_name: The ``ReferenceRecord`` field read for the served value, filters, and sorting.
    :return: A projection reading, filtering, and sorting on the ``field_name`` column.
    """

    def query(context: QueryContext, operator: str, literal: object) -> QueryExpression:
        value = context.field(field_name)
        if operator == "IS_UNKNOWN":
            return context.is_null(value)
        if operator == "IS_KNOWN":
            return context.not_(context.is_null(value))
        return context.compare(value, operator, context.constant(literal))

    return StoredPropertyProjection(
        response=lambda record: getattr(record, field_name),
        query=query,
        sort=lambda context: context.field(field_name),
    )


# A stored family serves an unprojected property as null, so every served
# ``references`` property is projected (``id``/``immutable_id``/``type`` are
# intrinsic to the store). Keys are the served (wire) property names.
cast(Any, ReferenceRecord).__httk_stored_properties__ = {
    **{
        item.name: _served_string(item.name)
        for item in fields(Reference)
        if item.name not in ("immutable_id", *_REFERENCE_NONSTRING_FIELDS)
    },
    "last_modified": StoredPropertyProjection(response=lambda record: getattr(record, "last_modified")),  # noqa: B009
    **{name: _served_persons(name) for name in _REFERENCE_PERSON_FIELDS},
}


__all__ = ["REFERENCES_DEFINITION_ID", "PersonRecord", "ReferenceEntry", "ReferenceRecord"]
