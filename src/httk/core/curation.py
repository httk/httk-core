"""Stdlib-only curation records: notes, tags, and external database entries.

Any stored entry can be weakly linked to a :class:`Note` (a dated remark), a
:class:`Tag` (a key with an optional value), and an :class:`ExternalDatabaseEntry`
(one entry of an external database), besides a
:class:`~httk.core.references.ReferenceRecord`. :data:`STANDARD_LINKS` declares
these four links and :func:`standard_links` tells which classes get them: every
entry record, that is a dataclass with both an ``id`` and an ``immutable_id``
field, except the four link targets themselves.

The records carry the internal, unprefixed entry-type names ``notes``, ``tags``
and ``external_database_entries``; the provider prefix is applied at the
serving edge. Like every record they are content-deduplicated, and weak links
bind lineages, so they stay local to one store.
"""

import datetime
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Annotated, Any, ClassVar, Self

from .references import ReferenceRecord
from .storage import IdentitySkip, Indexed, KeepStored, StorageInfo, Unique, WeakLink

NOTES_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/notes"
TAGS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/tags"
EXTERNAL_DATABASE_ENTRIES_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/external_database_entries"


def _check_text(value: Any, name: str, *, required: bool, stripped: bool = False) -> None:
    if value is None and not required:
        return
    if not isinstance(value, str):
        kind = "a str" if required else "a str or None"
        raise TypeError(f"Field '{name}' must be {kind}, got {type(value).__name__}.")
    if required and not value.strip():
        raise ValueError(f"Field '{name}' must be a nonempty string.")
    if stripped and value != value.strip():
        raise ValueError(f"Field '{name}' must not have surrounding whitespace.")


def _check_timestamp(value: Any, name: str, *, required: bool) -> None:
    if value is None and not required:
        return
    if not isinstance(value, datetime.datetime):
        raise TypeError(f"Field '{name}' must be a datetime, got {type(value).__name__}.")
    if value.utcoffset() is None:
        raise ValueError(f"Field '{name}' must be a timezone-aware datetime.")


@dataclass(frozen=True)
class Note:
    """A dated remark by some entity, linked from the entries it is about.

    Notes are content-deduplicated: the same date, source, and text is one
    entry, possibly linked from many entries. Code that wants to change a note
    for one linking entry only must therefore unlink the shared note and link a
    new one, rather than replace the shared note.

    :param date: When the note was made, a timezone-aware datetime chosen by its
        source; not the time it was stored.
    :param source: The entity that made the note: a person, a group, or a
        program with its version.
    :param text: The note itself, as free text.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises TypeError: If a field has the wrong type.
    :raises ValueError: If ``source`` or ``text`` is blank, or a timestamp is naive.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_note",
        identity_name="core_note",
        indexes=(("date",), ("source",)),
    )

    date: datetime.datetime
    source: str
    text: str
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "notes"

    def __post_init__(self) -> None:
        _check_timestamp(self.date, "date", required=True)
        _check_text(self.source, "source", required=True)
        _check_text(self.text, "text", required=True)
        _check_timestamp(self.last_modified, "last_modified", required=False)


@dataclass(frozen=True)
class Tag:
    """A key with an optional value that entries link to, to aid searching.

    :param key: The tag key.
    :param value: The optional tag value; None for a tag that only marks presence.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises TypeError: If a field has the wrong type.
    :raises ValueError: If ``key`` is blank or has surrounding whitespace, or ``last_modified`` is naive.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_tag",
        identity_name="core_tag",
        indexes=(("key", "value"),),
    )

    key: str
    value: str | None = None
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "tags"

    def __post_init__(self) -> None:
        _check_text(self.key, "key", required=True, stripped=True)
        _check_text(self.value, "value", required=False)
        _check_timestamp(self.last_modified, "last_modified", required=False)


@dataclass(frozen=True)
class ExternalDatabaseEntry:
    """One entry of an external database, linked from the entries related to it.

    ``database_provider`` names the provider of the external database: its
    OPTIMADE provider prefix (as registered in the OPTIMADE providers list),
    e.g. ``"cod"``, ``"oqmd"``, ``"mp"``, or an equivalent short lowercase name
    when no registered prefix exists. ``database`` identifies the specific
    database of that provider; None means the provider's only or main database.

    ``role`` says how the linking entry relates to the external entry and is
    part of the content identity: None for a general relation, ``"origin"``
    when the linking entry was obtained from the external entry. An entry may
    have several origins, unordered. ``url`` is outside the content identity, so
    the same external entry with and without a known URL is one entry. On a
    deduplicating save the first non-null ``url`` is kept and a later, different
    ``url`` is ignored (``KeepStored``); once a non-null ``url`` is stored it is
    kept: neither ``save`` nor ``replace`` changes it.

    The reference describing the whole external database is linked through this
    record's own ``references`` weak link.

    :param database_provider: The provider of the external database, by the convention above.
    :param database: The short identifier of the provider's database; None for its only or main one.
    :param entry_id: The identifier of the entry in that database, as that database writes it.
    :param url: A URL of the entry in that database, if available.
    :param role: How the linking entry relates to the external entry: None or ``"origin"``.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises TypeError: If a field has the wrong type.
    :raises ValueError: If ``database_provider``, ``database``, ``entry_id`` or ``role`` is blank
        or has surrounding whitespace, ``database_provider`` or ``database`` contains whitespace, or
        ``last_modified`` is naive.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_external_database_entry",
        identity_name="core_external_database_entry",
        indexes=(("database_provider", "database", "entry_id"), ("role",)),
        links=(WeakLink("references", ReferenceRecord, exposed_relationship=True),),
    )

    database_provider: str
    database: str | None
    entry_id: str
    url: Annotated[str | None, IdentitySkip(), KeepStored()] = field(default=None, compare=False)
    role: str | None = None
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "external_database_entries"

    def __post_init__(self) -> None:
        _check_text(self.database_provider, "database_provider", required=True, stripped=True)
        _check_text(self.database, "database", required=self.database is not None, stripped=True)
        for name in ("database_provider", "database"):
            if any(character.isspace() for character in getattr(self, name) or ""):
                raise ValueError(f"Field '{name}' must not contain whitespace.")
        _check_text(self.entry_id, "entry_id", required=True, stripped=True)
        _check_text(self.url, "url", required=False)
        _check_text(self.role, "role", required=self.role is not None, stripped=True)
        _check_timestamp(self.last_modified, "last_modified", required=False)


class NoteEntry:
    """Logical entry family for served :class:`Note` records.

    This family is not itself storable; store a ``Note`` directly.
    """

    type = "notes"
    definition_id = NOTES_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("NoteEntry is a logical entry family; store a Note directly")


class TagEntry:
    """Logical entry family for served :class:`Tag` records.

    This family is not itself storable; store a ``Tag`` directly.
    """

    type = "tags"
    definition_id = TAGS_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("TagEntry is a logical entry family; store a Tag directly")


class ExternalDatabaseEntryFamily:
    """Logical entry family for served :class:`ExternalDatabaseEntry` records.

    This family is not itself storable; store an ``ExternalDatabaseEntry`` directly.
    """

    type = "external_database_entries"
    definition_id = EXTERNAL_DATABASE_ENTRIES_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError(
            "ExternalDatabaseEntryFamily is a logical entry family; store an ExternalDatabaseEntry directly"
        )


#: The weak links every entry record gets without declaring them.
STANDARD_LINKS: tuple[WeakLink, ...] = (
    WeakLink("references", ReferenceRecord, exposed_relationship=True),
    WeakLink("notes", Note, exposed_relationship=True),
    WeakLink("tags", Tag, exposed_relationship=True),
    WeakLink("external", ExternalDatabaseEntry, exposed_relationship=True),
)

_LINK_TARGETS = frozenset({ReferenceRecord, Note, Tag, ExternalDatabaseEntry})


def standard_links(cls: type) -> tuple[WeakLink, ...]:
    """Return the standard weak links of a storable class.

    :param cls: The class to inspect.
    :return: :data:`STANDARD_LINKS` when ``cls`` is an entry record, a dataclass
        with both an ``id`` and an ``immutable_id`` field, other than the four link
        targets themselves; otherwise an empty tuple.
    """
    if not isinstance(cls, type) or not is_dataclass(cls) or cls in _LINK_TARGETS:
        return ()
    names = {item.name for item in fields(cls)}
    return STANDARD_LINKS if {"id", "immutable_id"} <= names else ()


__all__ = [
    "EXTERNAL_DATABASE_ENTRIES_DEFINITION_ID",
    "NOTES_DEFINITION_ID",
    "STANDARD_LINKS",
    "TAGS_DEFINITION_ID",
    "ExternalDatabaseEntry",
    "ExternalDatabaseEntryFamily",
    "Note",
    "NoteEntry",
    "Tag",
    "TagEntry",
    "standard_links",
]
