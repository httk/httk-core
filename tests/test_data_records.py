"""Tests for the core data records."""

import datetime
from dataclasses import replace

import pytest

from httk.core import DataRecord, DataRecordEntry, RunEdge
from httk.core.storage import content_id, project_storage_record


def test_from_value_is_canonical_and_round_trips() -> None:
    first = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"b": 2, "a": 1})
    second = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"a": 1, "b": 2})
    assert first.value_json == '{"a":1,"b":2}'
    assert first.value == {"a": 1, "b": 2}
    assert first.value_json == second.value_json
    assert content_id(first) == content_id(second)


def test_from_value_preserves_entry_ids() -> None:
    record = DataRecord.from_value(
        "https://example.org/def",
        "_httk_total_energy",
        1,
        id="httk.example-1-1",
        immutable_id="httk.example-1-1~1",
    )
    assert record.id == "httk.example-1-1"
    assert record.immutable_id == "httk.example-1-1~1"


@pytest.mark.parametrize("value_json", ['{"b":2,"a":1}', ' {"a":1,"b":2}', '{"a":1,"a":1}', '{"a":NaN}'])
def test_direct_value_json_must_be_canonical(value_json: str) -> None:
    with pytest.raises(ValueError, match="canonical JSON.*DataRecord.from_value"):
        DataRecord("https://example.org/def", "_httk_total_energy", value_json)


def test_direct_canonical_value_json_matches_from_value() -> None:
    direct = DataRecord("https://example.org/def", "_httk_total_energy", '{"a":1,"b":2}')
    created = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"b": 2, "a": 1})
    assert direct.value_json == created.value_json
    assert content_id(direct) == content_id(created)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 1.0), (1.5, 1.5), (10**400, None), (True, None), ("1", None), ([1], None), ({"a": 1}, None), (None, None)],
)
def test_value_number(value: object, expected: float | None) -> None:
    assert DataRecord.from_value("def", "name", value).value_number == expected


def test_create_validation_and_family() -> None:
    timestamp = datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC)
    record = DataRecord.from_obj(
        {"definition_id": "def", "name": "name", "value_json": "1", "last_modified": "2026-01-02T00:00:00+00:00"}
    )
    assert record.last_modified == timestamp
    with pytest.raises(ValueError, match="value_json"):
        DataRecord("def", "name", "not json")
    with pytest.raises(ValueError, match="Unknown field"):
        DataRecord.from_obj({"definition_id": "def", "name": "name", "value_json": "1", "extra": 1})
    assert DataRecordEntry.type == "records"
    assert DataRecordEntry.definition_id == "https://schemas.httk.org/defs/v0.1/entrytypes/records"
    with pytest.raises(TypeError, match="store a DataRecord directly"):
        DataRecordEntry()


def test_data_record_content_id_pin() -> None:
    record = DataRecord.from_value(
        "https://schemas.httk.org/defs/v0.1/properties/total-energy",
        "_httk_total_energy",
        {"b": 2, "a": 1},
        immutable_id="immutable",
        last_modified=datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
    )
    # A changed value means a storage-identity break; metadata is excluded.
    # Repinned Sep 19 2026: ``product_of`` joined the record content (identity-bearing StrongLink
    # edges), so every DataRecord content id changed; stores holding records must be rebuilt.
    assert content_id(record) == "825aab9e417bc726b1874f40b2ec61b6ba670409e0f087a6ccb2319b335764cc"
    identified = replace(record, id="logical", immutable_id="other-immutable")
    assert record.id is None
    assert identified.id == "logical"
    assert content_id(identified) == content_id(record)
    projected = DataRecord(**project_storage_record(DataRecord, identified))
    assert projected.id == "logical"
    assert projected.immutable_id == "other-immutable"


def test_product_of_edges_are_content_and_follow_the_run_edge_scheme() -> None:
    plain = DataRecord.from_value("https://schemas.httk.org/defs/v0.1/properties/total-energy", "e", -1.5)
    edge = RunEdge("subject", "structures", "httk.demo:1:s1")
    linked = DataRecord.from_value(plain.definition_id, "e", -1.5, product_of=[edge])
    assert plain.product_of == () and linked.product_of == (edge,)
    assert content_id(linked) != content_id(plain)  # the subject is part of the value's identity
    mapped = DataRecord.from_obj(
        {
            "definition_id": plain.definition_id,
            "name": "e",
            "value_json": plain.value_json,
            "product_of": [{"label": "subject", "entry_type": "structures", "entry_id": "httk.demo:1:s1"}],
        }
    )
    assert mapped == linked
    with pytest.raises(ValueError, match="Duplicate label"):
        DataRecord.from_value(plain.definition_id, "e", 1, product_of=[edge, RunEdge("subject", "runs", "r")])
