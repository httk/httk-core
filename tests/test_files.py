"""Tests for the core file records."""

import datetime
from typing import Any, cast

import pytest

from httk.core import File, FileEntry, FileRecord
from httk.core.files import FILES_DEFINITION_ID
from httk.core.register import (
    entry_record_info,
    known_entry_records,
    resolve_entry_family,
    resolve_entry_record,
)
from httk.core.storage import content_id


def _record(**metadata: object) -> FileRecord:
    return FileRecord(
        "https://example.org/files/plot.png",
        "plot.png",
        size=4096,
        media_type="image/png",
        version="v1",
        description="A generated plot",
        sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        **cast(Any, metadata),
    )


def test_file_record_content_id_and_metadata_exclusion() -> None:
    record = _record()
    # A changed value means a storage-identity break.
    assert content_id(record) == "efbd2362bb6b5578c1f0d11f74a8ad98e664096417b148fc408788acf503d050"
    assert record.id == content_id(record)
    assert record.type == "files"
    metadata = {
        "immutable_id": "immutable",
        "last_modified": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "url_stable_until": datetime.datetime(2027, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "modification_timestamp": datetime.datetime(2025, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "atime": datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "ctime": datetime.datetime(2023, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "mtime": datetime.datetime(2022, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
        "checksums": {"sha256": "different"},
    }
    assert content_id(_record(**metadata)) == content_id(record)


def test_file_entry_and_record_create() -> None:
    record = _record()
    assert isinstance(record, File)
    created = FileRecord.create(
        {
            "url": record.url,
            "name": record.name,
            "size": record.size,
            "media_type": record.media_type,
            "version": record.version,
            "description": record.description,
            "sha256": record.sha256,
        }
    )
    assert created == record
    assert FileRecord.create(record) is record
    with pytest.raises(ValueError, match="Unknown field"):
        FileRecord.create({"url": record.url, "name": record.name, "unknown": 1})
    assert FileEntry.type == "files"
    assert FileEntry.definition_id == FILES_DEFINITION_ID
    with pytest.raises(TypeError, match="store a FileRecord directly"):
        FileEntry()


def test_file_registry_registration() -> None:
    assert entry_record_info("core-file") == (
        "httk.core.files:FileRecord",
        "files",
        FILES_DEFINITION_ID,
    )
    assert known_entry_records(family="files") == ["core-file"]
    assert resolve_entry_record("core-file") is FileRecord
    assert cast(type[FileEntry], resolve_entry_family("files")).type == "files"
