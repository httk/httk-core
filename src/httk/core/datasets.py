"""Neutral dataset identity, distribution, and publication metadata contracts."""

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, ClassVar, Self, cast

from ._iris import is_absolute_iri as _is_absolute_iri
from .storage import StorageInfo

_DISTRIBUTION_FIELD_NAMES = frozenset({"id", "access_url", "media_type_iri", "format_iri", "byte_size", "sha256"})
_DATASET_REQUIRED_FIELD_NAMES = frozenset({"id", "title", "description", "publisher_id", "publisher_name"})
_DATASET_FIELD_NAMES = _DATASET_REQUIRED_FIELD_NAMES | {"distributions"}
_DATASET_FIELD_ORDER = ("id", "title", "description", "publisher_id", "publisher_name", "distributions")


def _unknown_fields(obj: Mapping[Any, Any], field_names: frozenset[str]) -> list[object]:
    """Return mapping keys that are not valid string field names."""

    return [key for key in obj if not isinstance(key, str) or key not in field_names]


def _format_unknown_fields(cls_name: str, unknown: list[object]) -> ValueError:
    """Build the standard unknown-field error for a mapping coercion."""

    names = ", ".join(sorted(repr(key) for key in unknown))
    return ValueError(f"Unknown field(s) for {cls_name}: {names}.")


@dataclass(frozen=True)
class DatasetDistribution:
    """Describe one retrievable representation of a dataset.

    Optional IRI fields must be well-formed absolute IRIs. ``byte_size`` is a
    non-negative integer, and ``sha256`` is a lowercase hexadecimal digest.

    :param id: An optional identifier for this representation.
    :param access_url: An optional URL from which the representation can be retrieved.
    :param media_type_iri: An optional IRI identifying the media type.
    :param format_iri: An optional IRI identifying the representation format.
    :param byte_size: The optional representation size in bytes.
    :param sha256: The optional lowercase SHA-256 digest.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_dataset_distribution_v1",
        identity_name="core_dataset_distribution_v1",
    )

    id: str | None = None
    access_url: str | None = None
    media_type_iri: str | None = None
    format_iri: str | None = None
    byte_size: int | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "access_url", "media_type_iri", "format_iri"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not _is_absolute_iri(value)):
                raise ValueError(f"Field '{field_name}' must be a well-formed absolute IRI or None.")
        if self.byte_size is not None and (
            isinstance(self.byte_size, bool) or not isinstance(self.byte_size, int) or self.byte_size < 0
        ):
            raise ValueError("Field 'byte_size' must be a non-negative integer or None.")
        if self.sha256 is not None and (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.sha256)
        ):
            raise ValueError("Field 'sha256' must be exactly 64 lowercase hexadecimal characters or None.")

    @classmethod
    def create(cls, obj: "DatasetDistribution | Mapping[str, Any]") -> Self:
        """Coerce a distribution instance or exact-field mapping.

        :param obj: A distribution instance or a mapping of distribution fields.
        :return: The existing or newly constructed distribution.
        :raises TypeError: If ``obj`` is neither a distribution nor a mapping.
        :raises ValueError: If the mapping has unknown or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, Mapping):
            raise TypeError(f"Expected a {cls.__name__} or a mapping, got {type(obj).__name__}.")
        unknown = _unknown_fields(obj, _DISTRIBUTION_FIELD_NAMES)
        if unknown:
            raise _format_unknown_fields(cls.__name__, unknown)
        return cls(**dict(obj))


def _normalize_distributions(value: object) -> tuple[DatasetDistribution, ...]:
    """Normalize and validate a dataset's distribution collection."""

    if not isinstance(value, Iterable):
        raise ValueError("Field 'distributions' must be an ordered non-string iterable of DatasetDistribution values.")
    if isinstance(value, str | Mapping | AbstractSet):
        raise ValueError("Field 'distributions' must be an ordered non-string iterable of DatasetDistribution values.")
    distributions = tuple(DatasetDistribution.create(item) for item in value)
    ids = [distribution.id for distribution in distributions if distribution.id is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("Field 'distributions' must not contain duplicate non-None distribution IDs.")
    return distributions


@dataclass(frozen=True)
class Dataset:
    """Describe one published dataset independently of a transport or provider.

    ``id`` and ``publisher_id`` are absolute IRIs.  The remaining fields are
    human-readable metadata and retain their supplied text exactly.

    :param id: The dataset's absolute IRI.
    :param title: The dataset's human-readable title.
    :param description: A non-empty description of the dataset.
    :param publisher_id: The publisher's absolute IRI.
    :param publisher_name: The publisher's human-readable name.
    :param distributions: The dataset's retrievable representations.
    """

    id: str
    title: str
    description: str
    publisher_id: str
    publisher_name: str
    distributions: tuple[DatasetDistribution, ...] = ()

    def __post_init__(self) -> None:
        for field_name in _DATASET_REQUIRED_FIELD_NAMES:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Field '{field_name}' must be a string containing non-whitespace text.")
        for field_name in ("id", "publisher_id"):
            if not _is_absolute_iri(getattr(self, field_name)):
                raise ValueError(f"Field '{field_name}' must be a well-formed absolute IRI.")
        object.__setattr__(self, "distributions", _normalize_distributions(self.distributions))

    @classmethod
    def create(cls, obj: "Dataset | Mapping[str, Any]") -> Self:
        """Coerce a mapping or existing dataset into a :class:`Dataset`.

        :param obj: A dataset instance or a mapping with exactly the dataset fields.
        :return: The existing or newly constructed dataset.
        :raises TypeError: If ``obj`` is neither a dataset nor a mapping.
        :raises ValueError: If the mapping has missing, unknown, or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, Mapping):
            raise TypeError(f"Expected a {cls.__name__} or a mapping, got {type(obj).__name__}.")
        missing = _DATASET_REQUIRED_FIELD_NAMES.difference(obj)
        if missing:
            raise ValueError(f"Missing required field(s) for {cls.__name__}: {', '.join(sorted(missing))}.")
        unknown = _unknown_fields(obj, _DATASET_FIELD_NAMES)
        if unknown:
            raise _format_unknown_fields(cls.__name__, unknown)
        return cls(**dict(obj))


@dataclass(frozen=True)
class DatasetRecord(Dataset):
    """Store one :class:`Dataset` using the core dataset storage contract.

    :param id: The dataset's absolute IRI.
    :param title: The dataset's human-readable title.
    :param description: A non-empty description of the dataset.
    :param publisher_id: The publisher's absolute IRI.
    :param publisher_name: The publisher's human-readable name.
    :param distributions: The dataset's retrievable representations.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_dataset_v1",
        identity_name="core_dataset_v1",
        indexes=(("id",), ("publisher_id",)),
    )
    __httk_canonical_source__ = Dataset

    @classmethod
    def __httk_project__(cls, source: Dataset) -> dict[str, object]:
        """Project a neutral dataset into record fields."""

        return {field_name: getattr(source, field_name) for field_name in _DATASET_FIELD_ORDER}

    @classmethod
    def create(cls, obj: "DatasetRecord | Dataset | Mapping[str, Any]") -> Self:
        """Coerce a dataset record, neutral dataset, or field mapping.

        :param obj: A dataset record, neutral dataset, or exact-field mapping.
        :return: The existing or newly constructed dataset record.
        :raises TypeError: If ``obj`` is not a dataset or mapping.
        :raises ValueError: If the mapping has unknown, missing, or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if isinstance(obj, Dataset):
            return cls(
                obj.id,
                obj.title,
                obj.description,
                obj.publisher_id,
                obj.publisher_name,
                obj.distributions,
            )
        return super().create(obj)


cast(Any, Dataset).__httk_storage_record__ = DatasetRecord


__all__ = ["Dataset", "DatasetDistribution", "DatasetRecord"]
