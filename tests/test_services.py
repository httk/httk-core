"""Tests for the neutral service metadata contract."""

from dataclasses import FrozenInstanceError

import pytest

from httk.core import Service, ServiceRecord, content_id
from httk.core.storage import project_storage_record, resolve_storage_record


def _service_fields() -> dict[str, object]:
    return {
        "id": "urn:uuid:550e8400-e29b-41d4-a716-446655440000",
        "title": " Example service ",
        "endpoint_url": "ftp://example.org/services/alpha",
        "conforms_to": ["https://www.w3.org/ns/dcat#DataService"],
    }


def test_service_create_accepts_valid_fields_and_normalizes_sequences() -> None:
    service = Service.create(
        {
            **_service_fields(),
            "serves_dataset_ids": ("urn:example:dataset:alpha",),
            "endpoint_description": "info:example/service-description",
        }
    )
    assert service.title == " Example service "
    assert service.conforms_to == ("https://www.w3.org/ns/dcat#DataService",)
    assert service.serves_dataset_ids == ("urn:example:dataset:alpha",)
    assert service.endpoint_description == "info:example/service-description"


def test_service_create_adopts_existing_instance_and_is_immutable_non_slots() -> None:
    service = Service.create(_service_fields())
    assert Service.create(service) is service
    assert hasattr(service, "__dict__")
    with pytest.raises(FrozenInstanceError):
        service.title = "Changed"


def test_service_accepts_non_http_absolute_iris() -> None:
    service = Service(
        id="urn:example:service:alpha",
        title="Service",
        endpoint_url="ftp://example.org/service",
        conforms_to=("info:example:profile",),
        serves_dataset_ids=("urn:example:dataset:alpha",),
        endpoint_description="mailto:services@example.org",
    )
    assert service.endpoint_url == "ftp://example.org/service"


def test_service_create_rejects_non_mapping_input() -> None:
    with pytest.raises(TypeError, match="Service or a mapping"):
        Service.create("not a service")


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"id": "https://example.org/services/alpha"}, "Missing required field"),
        ({**_service_fields(), "extra": "value"}, "Unknown field"),
    ],
)
def test_service_create_requires_allowed_field_set(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Service.create(fields)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", "services/alpha"),
        ("endpoint_url", "https://example.org/services/%ZZ"),
        ("endpoint_description", "#description"),
    ],
)
def test_service_rejects_relative_or_malformed_iris(field_name: str, value: str) -> None:
    fields = _service_fields()
    fields[field_name] = value
    with pytest.raises(ValueError, match=field_name):
        Service.create(fields)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("title", " ", "title"),
        ("conforms_to", (), "conforms_to"),
        ("conforms_to", "https://example.org/profile", "conforms_to"),
        ("conforms_to", {"https://example.org/profile"}, "conforms_to"),
        ("conforms_to", frozenset({"https://example.org/profile"}), "conforms_to"),
        ("conforms_to", {"https://example.org/profile": None}, "conforms_to"),
        ("conforms_to", ("https://example.org/profile", "https://example.org/profile"), "conforms_to"),
        ("conforms_to", ("relative-profile",), "conforms_to"),
        ("serves_dataset_ids", (), "serves_dataset_ids"),
        ("serves_dataset_ids", "https://example.org/datasets/alpha", "serves_dataset_ids"),
        ("serves_dataset_ids", {"https://example.org/datasets/alpha"}, "serves_dataset_ids"),
        ("serves_dataset_ids", frozenset({"https://example.org/datasets/alpha"}), "serves_dataset_ids"),
        ("serves_dataset_ids", {"https://example.org/datasets/alpha": None}, "serves_dataset_ids"),
        (
            "serves_dataset_ids",
            ("urn:example:dataset:alpha", "urn:example:dataset:alpha"),
            "serves_dataset_ids",
        ),
    ],
)
def test_service_rejects_invalid_text_or_iri_sequences(field_name: str, value: object, message: str) -> None:
    fields = _service_fields()
    fields[field_name] = value
    with pytest.raises(ValueError, match=message):
        Service.create(fields)


def test_service_record_projects_neutral_service_and_pins_content_id() -> None:
    service = Service.create(_service_fields())
    record = ServiceRecord.create(service)

    assert resolve_storage_record(service) is ServiceRecord
    assert project_storage_record(ServiceRecord, service) == {
        "id": service.id,
        "title": service.title,
        "endpoint_url": service.endpoint_url,
        "conforms_to": service.conforms_to,
        "serves_dataset_ids": None,
        "endpoint_description": None,
    }
    assert record == ServiceRecord.create(_service_fields())
    assert content_id(service) == "29f21392c2a44edb5a19a7db4d6ac6c5a439a912342de8a75de4858e781cce2f"
    assert content_id(record) == content_id(service)
