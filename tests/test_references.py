"""Tests for the core reference records."""

import datetime
from dataclasses import replace
from typing import Any, cast

import pytest

from httk.core import (
    AverageTotalEnergyRecord,
    DataRecord,
    DerivedDataRecord,
    FileRecord,
    PersonRecord,
    ReferenceEntry,
    ReferenceRecord,
    Run,
    TotalEnergyRecord,
    WeakLink,
)
from httk.core.references import REFERENCES_DEFINITION_ID
from httk.core.register import entry_record_info, known_entry_records, resolve_entry_family, resolve_entry_record
from httk.core.storage import content_id


def _reference(**metadata: object) -> ReferenceRecord:
    return ReferenceRecord(
        title="From ultrasoft pseudopotentials to the projector augmented-wave method",
        doi="10.1103/PhysRevB.59.1758",
        journal="Physical Review B",
        volume="59",
        pages="1758",
        year="1999",
        authors=({"name": "G. Kresse", "lastname": "Kresse"}, {"name": "D. Joubert"}),
        **cast(Any, metadata),
    )


def test_reference_record_coerces_persons_and_round_trips() -> None:
    record = ReferenceRecord(title="t", authors=({"name": "A"},))
    assert record.authors == (PersonRecord("A"),)
    assert record.editors is None
    assert record.type == "references"
    full = _reference(editors=[PersonRecord("E", firstname="Ed")])
    assert full.authors == (PersonRecord("G. Kresse", lastname="Kresse"), PersonRecord("D. Joubert"))
    assert full.editors == (PersonRecord("E", firstname="Ed"),)
    for value in (record, full, _reference(id="x", immutable_id="y")):
        assert eval(repr(value)) == value


def test_reference_record_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="unknown key"):
        ReferenceRecord(authors=({"name": "A", "email": "a@example.org"},))
    with pytest.raises(TypeError, match="year must be a str"):
        ReferenceRecord(year=cast(Any, 1999))
    with pytest.raises(TypeError, match="items must be PersonRecord or mappings"):
        ReferenceRecord(editors=cast(Any, ("A",)))
    with pytest.raises(TypeError, match="tuple or list"):
        ReferenceRecord(authors=cast(Any, "A"))
    with pytest.raises(ValueError, match="nonempty"):
        ReferenceRecord(authors=({"name": ""},))
    with pytest.raises(TypeError, match="lastname"):
        PersonRecord("A", lastname=cast(Any, 1))


def test_reference_record_content_identity() -> None:
    record = _reference()
    # A changed value means a storage-identity break.
    assert content_id(record) == "a73b4bd2473845c240407470ef8e3e180ba550c287f327fe6cd6a065175d77da"
    metadata = {
        "id": "logical",
        "immutable_id": "immutable",
        "last_modified": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
    }
    assert _reference(**metadata) == record
    assert content_id(_reference(**metadata)) == content_id(record)
    assert content_id(replace(record, year="2000")) != content_id(record)


def test_reference_stored_projections_serve_optimade_persons() -> None:
    projections = cast(Any, ReferenceRecord).__httk_stored_properties__
    record = _reference()
    assert projections["authors"].response(record) == [
        {"name": "G. Kresse", "lastname": "Kresse"},
        {"name": "D. Joubert"},
    ]
    assert projections["editors"].response(record) is None
    assert projections["doi"].response(record) == "10.1103/PhysRevB.59.1758"
    assert "immutable_id" not in projections
    for name, projection in projections.items():
        filterable = name not in ("authors", "editors", "last_modified")
        assert (projection.query is not None, projection.sort is not None) == (filterable, filterable), name


def test_stored_references_filter_and_sort_through_sql_store() -> None:
    sql = pytest.importorskip("httk.store.backend.sql")
    from httk.store import EntryIdScheme

    with sql.Backend.sqlite() as database:
        store = sql.SqlStore(
            database, entry_records={ReferenceEntry: ReferenceRecord}, entry_ids=EntryIdScheme("httk.test", "1")
        )
        store.save(_reference())
        store.save(ReferenceRecord(title="Other", year="2001"))
        federation = sql.StoredEntryFederation((sql.StoredEntrySource(store, ReferenceEntry, "references"),))

        (row,) = federation.query('doi="10.1103/PhysRevB.59.1758"').rows
        assert row["year"] == "1999"
        assert row["authors"] == [{"name": "G. Kresse", "lastname": "Kresse"}, {"name": "D. Joubert"}]
        assert [row["title"] for row in federation.query("doi IS UNKNOWN").rows] == ["Other"]
        assert [row["year"] for row in federation.query('year >= "2000"').rows] == ["2001"]
        titles = {
            descending: [row["title"] for row in federation.query(sort=(("title", descending),)).rows]
            for descending in (False, True)
        }
        assert titles[False] == sorted(titles[False]) == titles[True][::-1]


def test_reference_entry_family_registration() -> None:
    with pytest.raises(TypeError, match="logical entry family"):
        ReferenceEntry()
    family = cast(type[ReferenceEntry], resolve_entry_family("references"))
    assert family is ReferenceEntry
    assert family.type == "references"
    assert family.definition_id == REFERENCES_DEFINITION_ID
    assert known_entry_records(family="references") == ["core-reference-record"]
    assert resolve_entry_record("core-reference-record") is ReferenceRecord
    assert entry_record_info("core-reference-record")[1:] == ("references", REFERENCES_DEFINITION_ID)


@pytest.mark.parametrize(
    "record", [Run, DataRecord, DerivedDataRecord, TotalEnergyRecord, AverageTotalEnergyRecord, FileRecord]
)
def test_core_records_declare_exposed_references_link(record: type) -> None:
    links = cast(Any, record).__httk_storage__.links
    assert WeakLink("references", ReferenceRecord, exposed_relationship=True) in links
