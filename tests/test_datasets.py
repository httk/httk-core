"""Tests for the neutral dataset metadata contract."""

from dataclasses import FrozenInstanceError

import pytest

from httk.core import Dataset, DatasetDistribution, DatasetRecord, content_id
from httk.core.storage import project_storage_record, resolve_storage_record


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
    dataset = Dataset.from_obj(fields)
    assert dataset == Dataset(**fields)
    assert dataset.title == " Alpha dataset "
    assert dataset.description == " A focused dataset. "
    assert dataset.publisher_name == " Example publisher "


def test_dataset_accepts_non_http_absolute_iris() -> None:
    dataset = Dataset.from_obj({**_dataset_fields(), "id": "urn:uuid:550e8400-e29b-41d4-a716-446655440000"})
    assert dataset.id == "urn:uuid:550e8400-e29b-41d4-a716-446655440000"


def test_dataset_create_adopts_existing_instance_and_is_immutable() -> None:
    dataset = Dataset(**_dataset_fields())
    assert Dataset.from_obj(dataset) is dataset
    with pytest.raises(FrozenInstanceError):
        dataset.title = "Changed"


def test_dataset_create_rejects_non_mapping_input() -> None:
    with pytest.raises(TypeError, match="Dataset or a mapping"):
        Dataset.from_obj("not a dataset")


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"id": "https://example.org/datasets/alpha"}, "Missing required field"),
        ({**_dataset_fields(), "extra": "value"}, "Unknown field"),
    ],
)
def test_dataset_create_requires_exact_field_set(fields: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Dataset.from_obj(fields)


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
        Dataset.from_obj(fields)


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
        Dataset.from_obj(fields)


def test_dataset_distribution_create_accepts_optional_exact_fields() -> None:
    fields = {
        "id": "urn:example:distribution:alpha",
        "access_url": "https://example.org/datasets/alpha.json",
        "media_type_iri": "https://www.iana.org/assignments/media-types/application/json",
        "format_iri": "https://example.org/formats/json",
        "byte_size": 0,
        "sha256": "a" * 64,
    }
    distribution = DatasetDistribution.from_obj(fields)

    assert distribution == DatasetDistribution(**fields)
    assert DatasetDistribution.from_obj(distribution) is distribution
    assert DatasetDistribution.from_obj({}) == DatasetDistribution()


def test_dataset_distribution_accepts_root_relative_access_urls() -> None:
    distribution = DatasetDistribution(access_url="/files/dataset.csv?download=1")
    assert distribution.access_url == "/files/dataset.csv?download=1"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("id", "relative/distribution"),
        ("access_url", 1),
        ("access_url", "files/dataset.csv"),
        ("access_url", "//example.org/dataset.csv"),
        ("access_url", "/files/dataset.csv#fragment"),
        ("access_url", "/files/%ZZ"),
        ("media_type_iri", "https://example.org/%ZZ"),
        ("format_iri", "#format"),
        ("byte_size", -1),
        ("byte_size", True),
        ("byte_size", 1.5),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
    ],
)
def test_dataset_distribution_rejects_invalid_optional_fields(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match=field_name):
        DatasetDistribution.from_obj({field_name: value})


def test_dataset_distribution_create_rejects_unknown_and_non_string_mapping_keys() -> None:
    with pytest.raises(ValueError, match="Unknown field"):
        DatasetDistribution.from_obj({"unknown": None})
    with pytest.raises(ValueError, match="Unknown field"):
        DatasetDistribution.from_obj({1: None})  # type: ignore[dict-item]


def test_dataset_normalizes_distributions_and_rejects_duplicate_ids() -> None:
    values = (
        {"id": "urn:example:distribution:alpha"},
        DatasetDistribution(access_url="https://example.org/beta.json"),
    )
    dataset = Dataset(**_dataset_fields(), distributions=(value for value in values))

    assert dataset.distributions == (
        DatasetDistribution(id="urn:example:distribution:alpha"),
        DatasetDistribution(access_url="https://example.org/beta.json"),
    )
    with pytest.raises(ValueError, match="duplicate"):
        Dataset(
            **_dataset_fields(),
            distributions=(
                DatasetDistribution(id="urn:example:distribution:alpha"),
                DatasetDistribution(id="urn:example:distribution:alpha"),
            ),
        )
    Dataset(**_dataset_fields(), distributions=(DatasetDistribution(), DatasetDistribution()))


@pytest.mark.parametrize(
    "value",
    ["not a distribution iterable", 1, None, set(), frozenset(), {}],
)
def test_dataset_rejects_unordered_non_iterable_or_string_distributions(value: object) -> None:
    with pytest.raises(ValueError, match="distributions"):
        Dataset(**_dataset_fields(), distributions=value)  # type: ignore[arg-type]


def test_dataset_record_projects_neutral_dataset_and_pins_content_id() -> None:
    dataset = Dataset(**_dataset_fields())
    record = DatasetRecord.from_obj(dataset)

    assert resolve_storage_record(dataset) is DatasetRecord
    assert project_storage_record(DatasetRecord, dataset) == {
        "id": dataset.id,
        "title": dataset.title,
        "description": dataset.description,
        "publisher_id": dataset.publisher_id,
        "publisher_name": dataset.publisher_name,
        "distributions": (),
    }
    assert record == DatasetRecord.from_obj({**_dataset_fields(), "distributions": ()})
    assert content_id(dataset) == "fd31188af742a5ada767f7d943adf3025bbffb020fc69b5951977cd6f1ff178c"
    assert content_id(record) == content_id(dataset)


def test_dataset_distribution_and_nested_dataset_pin_content_ids() -> None:
    distribution = DatasetDistribution(
        id="urn:example:distribution:alpha",
        access_url="https://example.org/datasets/alpha.json",
        media_type_iri="https://www.iana.org/assignments/media-types/application/json",
        format_iri="https://example.org/formats/json",
        byte_size=42,
        sha256="a" * 64,
    )
    dataset = Dataset(**_dataset_fields(), distributions=(distribution,))
    record = DatasetRecord.from_obj(dataset)

    assert content_id(distribution) == "177726600ff23923940e2388328fa1014a1774070b5b13d6072288c0d9c5ce1e"
    assert content_id(dataset) == "bd9fcfc2db859c0debc5a6cfc6c3a5cc2d82a72fcc41c90eb7ff2a3b6a701173"
    assert content_id(record) == content_id(dataset)
