"""Tests for the curation records and the standard weak links."""

import datetime
from dataclasses import dataclass, replace
from typing import Any, cast

import pytest

from httk.core import (
    STANDARD_LINKS,
    ExternalDatabaseEntry,
    ExternalDatabaseEntryFamily,
    FileRecord,
    Note,
    NoteEntry,
    ReferenceRecord,
    Run,
    Tag,
    TagEntry,
    WeakLink,
    load_entry_type_definition,
    standard_links,
)
from httk.core.curation import EXTERNAL_DATABASE_ENTRIES_DEFINITION_ID, NOTES_DEFINITION_ID, TAGS_DEFINITION_ID
from httk.core.register import entry_record_info, known_entry_records, resolve_entry_family, resolve_entry_record
from httk.core.storage import content_id

_DATE = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.UTC)
_METADATA: dict[str, Any] = {
    "id": "logical",
    "immutable_id": "immutable",
    "last_modified": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
}


def _note(**metadata: Any) -> Note:
    return Note(_DATE, "httk-store 2.2.0", "Dropped an auxiliary loop to make the CIF parsable.", **metadata)


def _external(**metadata: Any) -> ExternalDatabaseEntry:
    return ExternalDatabaseEntry("cod", "1000000", role="origin", **metadata)


def test_records_construct() -> None:
    assert _note().type == "notes"
    assert Tag("source").value is None
    assert Tag("source", "cod").type == "tags"
    entry = ExternalDatabaseEntry("cod", "1000000", "https://www.crystallography.net/cod/1000000.html")
    assert (entry.url, entry.role, entry.type) == (
        "https://www.crystallography.net/cod/1000000.html",
        None,
        "external_database_entries",
    )
    assert ExternalDatabaseEntry("mp:legacy", "mp-149").database == "mp:legacy"


@pytest.mark.parametrize(
    ("build", "error"),
    [
        (lambda: Note(cast(Any, "2026-11-25"), "a", "t"), TypeError),
        (lambda: Note(_DATE.replace(tzinfo=None), "a", "t"), ValueError),
        (lambda: Note(_DATE, cast(Any, None), "t"), TypeError),
        (lambda: Note(_DATE, " ", "t"), ValueError),
        (lambda: Note(_DATE, "a", ""), ValueError),
        (lambda: Note(_DATE, "a", "t", last_modified=_DATE.replace(tzinfo=None)), ValueError),
        (lambda: Tag(cast(Any, 1)), TypeError),
        (lambda: Tag(""), ValueError),
        (lambda: Tag(" source"), ValueError),
        (lambda: Tag("source", cast(Any, 1)), TypeError),
        (lambda: ExternalDatabaseEntry(cast(Any, None), "1"), TypeError),
        (lambda: ExternalDatabaseEntry("", "1"), ValueError),
        (lambda: ExternalDatabaseEntry("my db", "1"), ValueError),
        (lambda: ExternalDatabaseEntry("cod ", "1"), ValueError),
        (lambda: ExternalDatabaseEntry("cod", cast(Any, 1)), TypeError),
        (lambda: ExternalDatabaseEntry("cod", " 1"), ValueError),
        (lambda: ExternalDatabaseEntry("cod", "1", url=cast(Any, 1)), TypeError),
        (lambda: ExternalDatabaseEntry("cod", "1", role=cast(Any, 1)), TypeError),
        (lambda: ExternalDatabaseEntry("cod", "1", role=""), ValueError),
        (lambda: ExternalDatabaseEntry("cod", "1", role="origin "), ValueError),
    ],
)
def test_records_reject_bad_values(build: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        build()


def test_content_identity_golden_pins() -> None:
    # A changed value means a storage-identity break.
    pins = {
        _note(): "1ce09f6e1f7233f2e3afbb75a05b0242aa8235c4bd5ce2324d06f1c876d0cbef",
        Tag("source", "cod"): "57ec6bc301a0852ae3963b79c03daa20dfb942780748328157889520c1fcbe3b",
        _external(): "a3cd6d6458f823b2834d34de2e1514f0f0a0390bdc4edde8f85460abe9451b4c",
    }
    for record, pin in pins.items():
        assert content_id(record) == pin
        with_metadata = replace(record, **_METADATA)
        assert with_metadata == record
        assert content_id(with_metadata) == pin


def test_external_entry_identity_ignores_url_but_not_role() -> None:
    record = _external()
    with_url = replace(record, url="https://www.crystallography.net/cod/1000000.html")
    assert with_url == record
    assert content_id(with_url) == content_id(record)
    general = replace(record, role=None)
    assert general != record
    assert content_id(general) != content_id(record)


@dataclass(frozen=True)
class _LocalEntry:
    value: int
    id: str | None = None
    immutable_id: str | None = None


@dataclass(frozen=True)
class _NoIds:
    value: int


@pytest.mark.parametrize(
    ("cls", "linked"),
    [
        (Run, True),
        (FileRecord, True),
        (_LocalEntry, True),
        (ReferenceRecord, False),
        (Note, False),
        (Tag, False),
        (ExternalDatabaseEntry, False),
        (_NoIds, False),
        (dict, False),
    ],
)
def test_standard_links(cls: type, linked: bool) -> None:
    assert standard_links(cls) == (STANDARD_LINKS if linked else ())


def test_standard_links_targets() -> None:
    assert [(link.name, link.target, link.exposed_relationship) for link in STANDARD_LINKS] == [
        ("references", ReferenceRecord, True),
        ("notes", Note, True),
        ("tags", Tag, True),
        ("external", ExternalDatabaseEntry, True),
    ]
    assert cast(Any, ExternalDatabaseEntry).__httk_storage__.links == (
        WeakLink("references", ReferenceRecord, exposed_relationship=True),
    )
    assert cast(Any, Note).__httk_storage__.links == cast(Any, Tag).__httk_storage__.links == ()


@pytest.mark.parametrize(
    ("record", "family", "name", "definition_id"),
    [
        (Note, NoteEntry, "core-note", NOTES_DEFINITION_ID),
        (Tag, TagEntry, "core-tag", TAGS_DEFINITION_ID),
        (
            ExternalDatabaseEntry,
            ExternalDatabaseEntryFamily,
            "core-external-database-entry",
            EXTERNAL_DATABASE_ENTRIES_DEFINITION_ID,
        ),
    ],
)
def test_definitions_and_registration(record: type, family: Any, name: str, definition_id: str) -> None:
    entry_type = family.type
    with pytest.raises(TypeError, match="logical entry family"):
        family()
    assert load_entry_type_definition(definition_id).name == entry_type
    assert resolve_entry_family(entry_type) is family
    assert family.definition_id == definition_id
    assert known_entry_records(family=entry_type) == [name]
    assert resolve_entry_record(name) is record
    assert entry_record_info(name)[1:] == (entry_type, definition_id)
    # The record's own ``type`` agrees with its family and definition.
    sample = {Note: _note, Tag: lambda: Tag("k"), ExternalDatabaseEntry: _external}[cast(Any, record)]()
    assert sample.type == entry_type
