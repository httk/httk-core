"""Tests for the neutral dataset metadata contract."""

from dataclasses import FrozenInstanceError

import pytest

from httk.core import Dataset


def _dataset_fields() -> dict[str, str]:
    return {
        "id": "https://example.org/datasets/alpha",
        "title": " Alpha dataset ",
        "description": " A focused dataset. ",
        "publisher_id": "https://example.org/publishers/example",
        "publisher_name": " Example publisher ",
    }


def test_dataset_create_accepts_valid_fields_and_preserves_text() -> None:
    fields = _dataset_fields()
    dataset = Dataset.create(fields)
    assert dataset == Dataset(**fields)
    assert dataset.title == " Alpha dataset "
    assert dataset.description == " A focused dataset. "
    assert dataset.publisher_name == " Example publisher "


def test_dataset_accepts_non_http_absolute_iris() -> None:
    dataset = Dataset.create({**_dataset_fields(), "id": "urn:uuid:550e8400-e29b-41d4-a716-446655440000"})
    assert dataset.id == "urn:uuid:550e8400-e29b-41d4-a716-446655440000"


def test_dataset_create_adopts_existing_instance_and_is_immutable() -> None:
    dataset = Dataset(**_dataset_fields())
    assert Dataset.create(dataset) is dataset
    with pytest.raises(FrozenInstanceError):
        dataset.title = "Changed"


def test_dataset_create_rejects_non_mapping_input() -> None:
    with pytest.raises(TypeError, match="Dataset or a mapping"):
        Dataset.create("not a dataset")


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"id": "https://example.org/datasets/alpha"}, "Missing required field"),
        ({**_dataset_fields(), "extra": "value"}, "Unknown field"),
    ],
)
def test_dataset_create_requires_exact_field_set(fields: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Dataset.create(fields)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("title", " "),
        ("description", ""),
        ("publisher_name", 1),
    ],
)
def test_dataset_rejects_empty_or_non_string_fields(field_name: str, value: object) -> None:
    fields = _dataset_fields()
    fields[field_name] = value  # type: ignore[assignment]
    with pytest.raises(ValueError, match=field_name):
        Dataset.create(fields)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", "dataset/alpha"),
        ("id", "#alpha"),
        ("id", "https://example.org/datasets/alpha\n"),
        ("id", "https://example.org/datasets/%ZZ"),
        ("id", "https://example.org/datasets/with|pipe"),
        ("id", "https://example.org/datasets/with\\backslash"),
        ("id", "https://example.org/datasets/<angle>"),
        ("id", "https://example.org/datasets/\ud800"),
        ("publisher_id", "publishers/example"),
        ("publisher_id", "https://example.org/publishers/example\x00"),
    ],
)
def test_dataset_rejects_relative_or_malformed_iris(field_name: str, value: str) -> None:
    fields = _dataset_fields()
    fields[field_name] = value
    with pytest.raises(ValueError, match=field_name):
        Dataset.create(fields)
