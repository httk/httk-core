"""Neutral service identity and endpoint metadata contract."""

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any, ClassVar, Self, cast

from ._iris import is_absolute_iri
from .storage import StorageInfo

_FIELD_NAMES = frozenset({"id", "title", "endpoint_url", "conforms_to", "serves_dataset_ids", "endpoint_description"})
_REQUIRED_FIELD_NAMES = frozenset({"id", "title", "endpoint_url", "conforms_to"})
_FIELD_ORDER = ("id", "title", "endpoint_url", "conforms_to", "serves_dataset_ids", "endpoint_description")


def _normalize_iri_sequence(field_name: str, value: object) -> tuple[str, ...]:
    """Normalize and validate one non-empty sequence of unique absolute IRIs."""

    if not isinstance(value, Iterable):
        raise ValueError(f"Field '{field_name}' must be a non-empty iterable of unique well-formed absolute IRIs.")
    if isinstance(value, str | Mapping | AbstractSet):
        raise ValueError(f"Field '{field_name}' must be a non-empty iterable of unique well-formed absolute IRIs.")
    values = tuple(value)
    if not values:
        raise ValueError(f"Field '{field_name}' must be a non-empty iterable of unique well-formed absolute IRIs.")
    if any(not isinstance(item, str) or not is_absolute_iri(item) for item in values):
        raise ValueError(f"Field '{field_name}' must contain only well-formed absolute IRIs.")
    if len(set(values)) != len(values):
        raise ValueError(f"Field '{field_name}' must not contain duplicate IRIs.")
    return values


@dataclass(frozen=True)
class Service:
    """Describe one service independently of its publication transport.

    The service and endpoint identifiers are absolute IRIs; this neutral core
    contract does not impose a particular scheme.  ``conforms_to`` names one
    or more standards the service implements, and may be supplied as any
    ordered non-string iterable.

    :param id: The service's absolute IRI.
    :param title: The service's human-readable title.
    :param endpoint_url: The service endpoint's absolute IRI.
    :param conforms_to: Non-empty unique absolute IRIs for implemented standards.
    :param serves_dataset_ids: Optional non-empty unique absolute IRIs for served datasets.
    :param endpoint_description: An optional absolute IRI describing the endpoint.
    """

    id: str
    title: str
    endpoint_url: str
    conforms_to: tuple[str, ...]
    serves_dataset_ids: tuple[str, ...] | None = None
    endpoint_description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Field 'title' must be a string containing non-whitespace text.")
        for field_name in ("id", "endpoint_url"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not is_absolute_iri(value):
                raise ValueError(f"Field '{field_name}' must be a well-formed absolute IRI.")
        object.__setattr__(self, "conforms_to", _normalize_iri_sequence("conforms_to", self.conforms_to))
        if self.serves_dataset_ids is not None:
            object.__setattr__(
                self,
                "serves_dataset_ids",
                _normalize_iri_sequence("serves_dataset_ids", self.serves_dataset_ids),
            )
        if self.endpoint_description is not None and (
            not isinstance(self.endpoint_description, str) or not is_absolute_iri(self.endpoint_description)
        ):
            raise ValueError("Field 'endpoint_description' must be a well-formed absolute IRI.")

    @classmethod
    def create(cls, obj: "Service | Mapping[str, Any]") -> Self:
        """Coerce a mapping or existing service into a :class:`Service`.

        :param obj: A service instance or a mapping with service fields.
        :return: The existing or newly constructed service.
        :raises TypeError: If ``obj`` is neither a service nor a mapping.
        :raises ValueError: If the mapping has missing, unknown, or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if not isinstance(obj, Mapping):
            raise TypeError(f"Expected a {cls.__name__} or a mapping, got {type(obj).__name__}.")
        missing = _REQUIRED_FIELD_NAMES.difference(obj)
        if missing:
            raise ValueError(f"Missing required field(s) for {cls.__name__}: {', '.join(sorted(missing))}.")
        unknown = [key for key in obj if not isinstance(key, str) or key not in _FIELD_NAMES]
        if unknown:
            raise ValueError(f"Unknown field(s) for {cls.__name__}: {', '.join(sorted(repr(key) for key in unknown))}.")
        return cls(**dict(obj))


@dataclass(frozen=True)
class ServiceRecord(Service):
    """Store one :class:`Service` using the core service storage contract.

    :param id: The service's absolute IRI.
    :param title: The service's human-readable title.
    :param endpoint_url: The service endpoint's absolute IRI.
    :param conforms_to: Non-empty unique absolute IRIs for implemented standards.
    :param serves_dataset_ids: Optional non-empty unique absolute IRIs for served datasets.
    :param endpoint_description: An optional absolute IRI describing the endpoint.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_service_v1",
        identity_name="core_service_v1",
        indexes=(("id",), ("endpoint_url",)),
    )
    __httk_canonical_source__ = Service

    @classmethod
    def __httk_project__(cls, source: Service) -> dict[str, object]:
        """Project a neutral service into record fields."""

        return {field_name: getattr(source, field_name) for field_name in _FIELD_ORDER}

    @classmethod
    def create(cls, obj: "ServiceRecord | Service | Mapping[str, Any]") -> Self:
        """Coerce a service record, neutral service, or field mapping.

        :param obj: A service record, neutral service, or service field mapping.
        :return: The existing or newly constructed service record.
        :raises TypeError: If ``obj`` is not a service or mapping.
        :raises ValueError: If the mapping has unknown, missing, or invalid fields.
        """

        if isinstance(obj, cls):
            return obj
        if isinstance(obj, Service):
            return cls(
                obj.id,
                obj.title,
                obj.endpoint_url,
                obj.conforms_to,
                obj.serves_dataset_ids,
                obj.endpoint_description,
            )
        return super().create(obj)


cast(Any, Service).__httk_storage_record__ = ServiceRecord


__all__ = ["Service", "ServiceRecord"]
