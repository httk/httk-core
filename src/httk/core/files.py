"""Stdlib-only storage records for OPTIMADE ``files`` entries.

``FileRecord`` stores file metadata and a flat ``sha256`` digest. Files are
deduplicated by content: identity is the media type, the httk format name when
set, and the SHA-256 digest, so every path to the same bytes is one entry.
A record with ``url=None`` names content whose bytes are lost (known only by
digest) and serves its ``url`` as an RFC 6920 ``ni:///sha-256;...`` URI.
The mapping-valued ``checksums`` field is skipped because SQL storage cannot
persist mappings; use ``sha256`` for the storable digest.
"""

import base64
import datetime
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Self, cast

from .entry_types import File
from .references import ReferenceRecord
from .storage import (
    IdentitySkip,
    IdentitySkipWhenNone,
    Indexed,
    KeepStored,
    Skip,
    StorageInfo,
    StoredPropertyProjection,
    Unique,
    WeakLink,
)

FILES_DEFINITION_ID = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"


@dataclass(frozen=True)
class FileRecord(File):
    """Store one OPTIMADE ``files`` entry with content identity metadata.

    A file record is identified by its content: the media type, the httk
    ``format`` name when set, and the SHA-256 digest of the bytes. URL and name
    remain required positional fields, but they only say where the bytes
    currently live and are excluded from content identity; a record may be
    re-pointed to any copy whose bytes still match ``sha256``, and the same
    bytes used in many places are one entry. The human-readable and immutable
    identifiers, size, version, description, timestamps, and other metadata
    are excluded from content identity as well. A repeated save of the same
    content keeps each stored non-null location and metadata value and fills
    each stored null from the incoming record (first non-null wins), so a lost
    file (``url=None``) gets its location from a later save of the same bytes.
    ``checksums`` is skipped because mapping fields are not SQL-storable;
    store the flat ``sha256`` value when a storable digest is needed.
    ``url`` is None when the bytes are lost: the record then names content that
    existed (its digest) but has no location; served as an ``ni:`` URI.

    :param url: The URL to get the contents of the file, or None when the bytes are lost.
    :param name: The base name of the file.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :param url_stable_until: The optional URL stability deadline.
    :param size: The file size in bytes, if known.
    :param media_type: The file MIME type; ``"application/octet-stream"`` when nothing more specific is known.
    :param version: The file version, if known.
    :param modification_timestamp: The optional content modification timestamp.
    :param description: An optional free-form file description.
    :param checksums: Optional checksums, kept out of SQL storage.
    :param atime: The optional POSIX access timestamp.
    :param ctime: The optional POSIX status-change timestamp.
    :param mtime: The optional POSIX modification timestamp.
    :param sha256: The flat SHA-256 hexadecimal digest of the file bytes; required, keyword-only.
    :param format: The httk reader format name usable as ``httk.core.load(path, format=...)`` (e.g. ``"poscar"``), if known; part of identity only when set.
    :raises TypeError: If ``url`` is neither a string nor None.
    :raises ValueError: If ``sha256`` is not a lowercase hexadecimal SHA-256 digest.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_file",
        identity_name="core_file",
        indexes=(("url",), ("name",), ("sha256",)),
        links=(WeakLink("references", ReferenceRecord, exposed_relationship=True),),
    )

    # A lost-bytes record widens the generated ``File.url: str``; served as an ``ni:`` URI.
    url: Annotated[str | None, IdentitySkip(), KeepStored()]  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]
    name: Annotated[str, IdentitySkip(), KeepStored()]
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(
        default=None, compare=False
    )
    url_stable_until: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(
        default=None, compare=False
    )
    size: Annotated[int | None, IdentitySkip(), KeepStored()] = None
    media_type: str = "application/octet-stream"
    version: Annotated[str | None, IdentitySkip(), KeepStored()] = None
    modification_timestamp: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(
        default=None, compare=False
    )
    description: Annotated[str | None, IdentitySkip(), KeepStored()] = None
    checksums: Annotated[Mapping[str, str] | None, Skip()] = None
    atime: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(default=None, compare=False)
    ctime: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(default=None, compare=False)
    mtime: Annotated[datetime.datetime | None, IdentitySkip(), KeepStored()] = field(default=None, compare=False)
    sha256: str = field(kw_only=True)
    format: Annotated[str | None, IdentitySkipWhenNone()] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.url is not None and not isinstance(self.url, str):
            raise TypeError(f"FileRecord url must be a str or None, got {type(self.url).__name__}")
        if not isinstance(self.sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError(f"FileRecord sha256 must be a lowercase hex SHA-256 digest, got {self.sha256!r}")

    @property
    def type(self) -> str:
        """Return the served entry type name."""
        return "files"


class FileEntry:
    """Logical entry family for served :class:`FileRecord` records.

    This family is not itself storable; store a ``FileRecord`` directly.
    """

    type = "files"
    definition_id = FILES_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("FileEntry is a logical entry family; store a FileRecord directly")


def _served_file_value(field_name: str) -> StoredPropertyProjection:
    """Return a response-only projection reading one served ``FileRecord`` field.

    The served ``files`` properties map directly onto stored columns, so the
    projection reads the field verbatim; filtering and sorting are intentionally
    omitted (files are reached by id through their producing run's edges, not
    filtered by metadata).

    :param field_name: The ``FileRecord`` field read for the served value.
    :return: A projection whose response reads ``field_name`` directly.
    """
    return StoredPropertyProjection(response=lambda record: getattr(record, field_name))


def _content_uri(sha256: str) -> str:
    """Return the RFC 6920 ``ni:`` URI naming the bytes with SHA-256 digest *sha256*.

    :param sha256: The lowercase hexadecimal SHA-256 digest.
    :return: ``ni:///sha-256;`` followed by the unpadded base64url digest.
    """
    return "ni:///sha-256;" + base64.urlsafe_b64encode(bytes.fromhex(sha256)).rstrip(b"=").decode("ascii")


def _served_url(served: object) -> str:
    """Return the served ``url``, a content ``ni:`` URI when the bytes are lost.

    OPTIMADE requires a string ``url``, so a ``url=None`` record serves the URI
    naming its bytes by digest instead of claiming a location.

    :param served: The ``FileRecord`` whose url is served.
    :return: The stored url, or the record's ``ni:`` content URI.
    """
    record = cast(FileRecord, served)
    return _content_uri(record.sha256) if record.url is None else record.url


def _served_checksums(served: object) -> Mapping[str, str]:
    """Return the served ``checksums``, derived from the flat ``sha256`` when unset.

    ``checksums`` is not SQL-storable, so a stored record serves its ``sha256``
    digest as ``{"sha256": ...}``, as the in-memory files provider does; an
    explicit ``checksums`` mapping wins.

    :param served: The ``FileRecord`` whose checksums are served.
    :return: The served checksums mapping.
    """
    record = cast(FileRecord, served)
    if record.checksums is not None:
        return record.checksums
    return {"sha256": record.sha256}


# Default projections so ``StoredEntrySource(store, FileEntry, ...)`` resolves (a
# stored source rejects a family whose non-nullable served properties ``url`` and
# ``name`` have no response mapping) and serves every stored ``files`` property;
# an unprojected property would be served as null. ``sha256`` is not an OPTIMADE
# ``files`` property, so it is served through ``checksums`` instead. Keys are the
# served (wire) ``files`` property names.
cast(Any, FileRecord).__httk_stored_properties__ = {
    "url": StoredPropertyProjection(response=_served_url),
    **{
        name: _served_file_value(name)
        for name in (
            "name",
            "url_stable_until",
            "size",
            "media_type",
            "version",
            "modification_timestamp",
            "description",
            "atime",
            "ctime",
            "mtime",
        )
    },
    "checksums": StoredPropertyProjection(response=_served_checksums),
}


__all__ = ["FILES_DEFINITION_ID", "FileEntry", "FileRecord"]
