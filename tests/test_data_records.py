"""Tests for the core data records."""

import datetime

import pytest

from httk.core import DataRecord, DataRecordEntry
from httk.core.storage import content_id


def test_from_value_is_canonical_and_round_trips() -> None:
    first = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"b": 2, "a": 1})
    second = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"a": 1, "b": 2})
    assert first.value_json == '{"a":1,"b":2}'
    assert first.value == {"a": 1, "b": 2}
    assert first.value_json == second.value_json
    assert first.id == second.id


@pytest.mark.parametrize("value_json", ['{"b":2,"a":1}', ' {"a":1,"b":2}', '{"a":1,"a":1}', '{"a":NaN}'])
def test_direct_value_json_must_be_canonical(value_json: str) -> None:
    with pytest.raises(ValueError, match="canonical JSON.*DataRecord.from_value"):
        DataRecord("https://example.org/def", "_httk_total_energy", value_json)


def test_direct_canonical_value_json_matches_from_value() -> None:
    direct = DataRecord("https://example.org/def", "_httk_total_energy", '{"a":1,"b":2}')
    created = DataRecord.from_value("https://example.org/def", "_httk_total_energy", {"b": 2, "a": 1})
    assert direct.value_json == created.value_json
    assert direct.id == created.id


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
    assert DataRecordEntry.type == "_httk_records"
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
    assert content_id(record) == "04e3a194913be8367d0df153a98cc07a6eb34640268c26580ad253ae740be140"
