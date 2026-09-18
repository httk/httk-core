"""Tests for tolerating optional OPTIMADE timestamps that lack a UTC offset."""

import datetime
import logging

import pytest

from httk.core.entry_types import Reference
from httk.core.optimade import (
    IncompleteOptimadeResourceError,
    OptimadeDocument,
    OptimadeReference,
    OptimadeResource,
    OptimadeSchemaSnapshot,
    ReferenceView,
    decode_optional_timestamp,
)
from httk.core.optimade.entries import _decode_by_payload, _naive_timestamp_origins_warned

_PROPERTY_BASE = "https://schemas.optimade.org/defs/v1.2/properties/core/"


def _reference_resource(attributes: str, *, source_url: str = "https://example.test/v1/references") -> OptimadeResource:
    properties = {
        "identifier-renamed": _PROPERTY_BASE + "id",
        "record-type-renamed": _PROPERTY_BASE + "type",
        "stable-renamed": _PROPERTY_BASE + "immutable_id",
        "changed-renamed": _PROPERTY_BASE + "last_modified",
        "title-renamed": "https://schemas.optimade.org/defs/v1.2/properties/optimade/references/title",
    }
    info_properties = ", ".join(f'"{remote}": {{"$id": "{iri}"}}' for remote, iri in properties.items())
    info = OptimadeDocument(
        f'{{"data": {{"properties": {{{info_properties}}}}}}}',
        "https://example.test/v1/info/references",
    )
    document = OptimadeDocument(
        f'{{"data": [{{"id": "entry-1", "type": "transport-references", "attributes": {attributes}}}]}}',
        source_url,
    )
    return OptimadeResource(document, 0, OptimadeSchemaSnapshot("references", info))


def test_offset_bearing_string_decodes() -> None:
    decoded = decode_optional_timestamp("2024-02-03T04:05:06+02:00", source_url="https://example.test/v1")
    assert decoded == datetime.datetime(2024, 2, 3, 4, 5, 6, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))
    assert decoded is not None and decoded.utcoffset() == datetime.timedelta(hours=2)


def test_zulu_suffix_decodes_to_utc() -> None:
    decoded = decode_optional_timestamp("2024-02-03T04:05:06Z", source_url="https://example.test/v1")
    assert decoded is not None
    assert decoded.tzinfo is not None
    assert decoded.utcoffset() == datetime.timedelta(0)


def test_none_decodes_to_none() -> None:
    assert decode_optional_timestamp(None, source_url="https://example.test/v1") is None


def test_naive_string_is_unknown_and_warns_once_per_origin(caplog: pytest.LogCaptureFixture) -> None:
    _naive_timestamp_origins_warned.clear()
    caplog.set_level(logging.WARNING, logger="httk.core.optimade.entries")

    assert decode_optional_timestamp("2023-02-11T01:06:23.403000", source_url="https://a.example/v1/refs/1") is None
    # Same origin, different path: no additional warning.
    assert decode_optional_timestamp("2023-02-11T01:06:23.403000", source_url="https://a.example/v1/refs/2") is None
    # Distinct origin: a second warning.
    assert decode_optional_timestamp("2023-02-11T01:06:23.403000", source_url="https://b.example/v1/refs/1") is None

    warnings = [record for record in caplog.records if "without a UTC offset" in record.getMessage()]
    assert len(warnings) == 2
    assert all(getattr(record, "context", None) == "optimade" for record in warnings)
    assert "https://a.example" in warnings[0].getMessage()
    assert "https://b.example" in warnings[1].getMessage()


def test_space_separated_naive_datetime_is_unknown(caplog: pytest.LogCaptureFixture) -> None:
    _naive_timestamp_origins_warned.clear()
    caplog.set_level(logging.WARNING, logger="httk.core.optimade.entries")
    assert decode_optional_timestamp("2023-02-11 01:06:23", source_url="https://a.example/v1") is None
    warnings = [r for r in caplog.records if "without a UTC offset" in r.getMessage()]
    assert len(warnings) == 1


def test_non_string_value_raises() -> None:
    with pytest.raises(ValueError):
        decode_optional_timestamp(1700000000, source_url="https://example.test/v1")


def test_unparseable_string_raises() -> None:
    with pytest.raises(ValueError, match="invalid RFC3339 timestamp"):
        decode_optional_timestamp("not-a-timestamp", source_url="https://example.test/v1")


def test_bare_date_raises_not_treated_as_naive_timestamp() -> None:
    # fromisoformat accepts a bare date, but it is not an RFC 3339 timestamp.
    with pytest.raises(ValueError, match="invalid RFC3339 timestamp"):
        decode_optional_timestamp("2024-02-03", source_url="https://example.test/v1")


def test_hour_minute_form_without_seconds_raises() -> None:
    with pytest.raises(ValueError, match="invalid RFC3339 timestamp"):
        decode_optional_timestamp("2024-02-03T04:05", source_url="https://example.test/v1")


def test_seconds_zulu_decodes() -> None:
    decoded = decode_optional_timestamp("2023-02-11T01:06:23Z", source_url="https://example.test/v1")
    assert decoded is not None
    assert decoded.utcoffset() == datetime.timedelta(0)


def test_backend_naive_last_modified_is_none_but_immutable_id_decodes() -> None:
    _naive_timestamp_origins_warned.clear()
    resource = _reference_resource('{"stable-renamed": "immutable-1", "changed-renamed": "2023-02-11T01:06:23.403000"}')
    backend = OptimadeReference(resource)
    assert backend.last_modified is None
    assert backend.immutable_id == "immutable-1"


def test_backend_offset_last_modified_decodes() -> None:
    resource = _reference_resource('{"changed-renamed": "2024-02-03T04:05:06Z"}')
    backend = OptimadeReference(resource)
    assert backend.last_modified is not None
    assert backend.last_modified.tzinfo is not None


def test_backend_non_string_last_modified_raises() -> None:
    resource = _reference_resource('{"changed-renamed": 123}')
    backend = OptimadeReference(resource)
    with pytest.raises(IncompleteOptimadeResourceError, match="last_modified"):
        _ = backend.last_modified


def test_view_record_naive_last_modified_is_none_and_dedups_with_backend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _naive_timestamp_origins_warned.clear()
    caplog.set_level(logging.WARNING, logger="httk.core.optimade.entries")
    resource = _reference_resource(
        '{"stable-renamed": "immutable-1", "changed-renamed": "2023-02-11T01:06:23.403000", '
        '"title-renamed": "A reference"}'
    )
    backend = OptimadeReference(resource)
    # Backend accessor and record materialization both hit the naive value.
    assert backend.last_modified is None
    record = ReferenceView(backend).record
    assert isinstance(record, Reference)
    assert record.last_modified is None
    assert record.title == "A reference"
    assert record.immutable_id == "immutable-1"
    warnings = [r for r in caplog.records if "without a UTC offset" in r.getMessage()]
    assert len(warnings) == 1


def test_required_timestamp_still_rejects_naive_value() -> None:
    payload = {"x-optimade-type": "timestamp"}
    with pytest.raises(ValueError, match="must include a UTC offset"):
        _decode_by_payload(payload, "2023-02-11T01:06:23.403000")
