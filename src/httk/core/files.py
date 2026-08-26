"""Stdlib-only storage records for OPTIMADE ``files`` entries.

``FileRecord`` stores file metadata and a flat ``sha256`` digest. The URL is
part of identity deliberately: two paths to the same bytes are two entries.
The mapping-valued ``checksums`` field is skipped because SQL storage cannot
persist mappings; use ``sha256`` for the storable digest.
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, Self

from .entry_types import File
from .storage import IdentitySkip, Indexed, Skip, StorageInfo, Unique

FILES_DEFINITION_ID = "https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files"


@dataclass(frozen=True)
class FileRecord(File):
    """Store one OPTIMADE ``files`` entry with content identity metadata.

    URL and name remain required positional fields. The URL is included in
    identity so separate paths to identical bytes remain separate entries.
    The human-readable and immutable identifiers, metadata timestamps, and
    other metadata are excluded from content identity.
    ``checksums`` is skipped because mapping fields are not SQL-storable;
    store the flat ``sha256`` value when a storable digest is needed.

    :param url: The URL to get the contents of the file.
    :param name: The base name of the file.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :param url_stable_until: The optional URL stability deadline.
    :param size: The file size in bytes, if known.
    :param media_type: The file MIME type, if known.
    :param version: The file version, if known.
    :param modification_timestamp: The optional content modification timestamp.
    :param description: An optional free-form file description.
    :param checksums: Optional checksums, kept out of SQL storage.
    :param atime: The optional POSIX access timestamp.
    :param ctime: The optional POSIX status-change timestamp.
    :param mtime: The optional POSIX modification timestamp.
    :param sha256: The optional flat SHA-256 digest.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_file",
        identity_name="core_file",
        indexes=(("url",), ("name",), ("sha256",)),
    )

    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    url_stable_until: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    size: int | None = None
    media_type: str | None = None
    version: str | None = None
    modification_timestamp: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    description: str | None = None
    checksums: Annotated[Mapping[str, str] | None, Skip()] = None
    atime: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    ctime: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    mtime: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)
    sha256: str | None = None

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


__all__ = ["FILES_DEFINITION_ID", "FileEntry", "FileRecord"]
