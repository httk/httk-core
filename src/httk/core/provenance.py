"""Stdlib-only OPTIMADE-aligned calculation provenance records.

Runs are served as provider-prefixed ``_httk_runs`` entries. Their
``has_input``/``has_artifact``/``has_output`` relationships are represented by
loose labeled references rather than object references: inputs are consumed,
artifacts are created, and outputs are returned. The single-creator rule for
artifacts is a serving concern and is not enforced on an individual record.
The definition identity remains the unprefixed ``RUNS_DEFINITION_ID`` IRI.
"""

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from typing import Annotated, Any, ClassVar, Self

from .storage import IdentitySkip, StorageInfo, content_id

RUNS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/runs"
_TIMESTAMP_FIELDS = frozenset({"last_modified"})


def _validate_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string without surrounding whitespace.")


def _validate_uri(value: Any, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value or value != value.strip()):
        raise ValueError(f"Field '{field_name}' must be a non-empty string without surrounding whitespace or None.")


def _validate_timestamp(value: Any, field_name: str) -> None:
    if value is not None and (not isinstance(value, datetime.datetime) or value.utcoffset() is None):
        raise ValueError(f"Field '{field_name}' must be a timezone-aware datetime with an explicit offset.")


def _create(cls: type[Any], obj: Any) -> Any:
    if isinstance(obj, cls):
        return obj
    if not isinstance(obj, Mapping):
        raise TypeError(f"Expected a {cls.__name__} or a mapping, got {type(obj).__name__}.")
    known = {item.name for item in fields(cls)}
    unknown = [key for key in obj if key not in known]
    if unknown:
        raise ValueError("Unknown field(s) for " + cls.__name__ + ": " + ", ".join(sorted(unknown)) + ".")
    values = dict(obj)
    for field_name in _TIMESTAMP_FIELDS & known:
        value = values.get(field_name)
        if isinstance(value, str):
            try:
                value = datetime.datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"Invalid ISO-8601 value for field '{field_name}': {value!r}.") from exc
            _validate_timestamp(value, field_name)
            values[field_name] = value
        elif value is not None:
            _validate_timestamp(value, field_name)
    return cls(**values)


def _edges(values: Iterable[Any]) -> "tuple[RunEdge, ...]":
    return tuple(RunEdge.create(value) for value in values)


@dataclass(frozen=True)
class RunEdge:
    """One loose labeled reference from a run to another entry."""

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_run_edge_v1", identity_name="core_run_edge_v1"
    )

    label: str
    entry_type: str
    entry_id: str

    def __post_init__(self) -> None:
        for field_name in ("label", "entry_type", "entry_id"):
            _validate_string(getattr(self, field_name), field_name)

    @classmethod
    def create(cls, obj: "RunEdge | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class Run:
    """One workflow execution with loose provenance edges.

    ``inputs`` are ``has_input`` edges to consumed entries, ``artifacts`` are
    ``has_artifact`` edges to created entries, and ``outputs`` are
    ``has_output`` edges to returned entries. Artifact single-creator
    exclusivity across runs is documented here, not enforced per record.

    Every invariant is cheap and total, so there is deliberately no
    ``__httk_validate__`` hook.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_run_v1",
        identity_name="core_run_v1",
        indexes=(("workflow_declaration_uri",), ("immutable_id",), ("last_modified",)),
    )

    workflow_declaration_uri: str | None = None
    inputs: tuple[RunEdge, ...] = ()
    artifacts: tuple[RunEdge, ...] = ()
    outputs: tuple[RunEdge, ...] = ()
    immutable_id: Annotated[str | None, IdentitySkip()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        return "_httk_runs"

    @property
    def id(self) -> str:
        return content_id(self)

    def __post_init__(self) -> None:
        _validate_uri(self.workflow_declaration_uri, "workflow_declaration_uri")
        for side in ("inputs", "artifacts", "outputs"):
            values = _edges(getattr(self, side))
            labels: set[str] = set()
            for edge in values:
                if edge.label in labels:
                    raise ValueError(f"Duplicate label {edge.label!r} on Run {side}.")
                labels.add(edge.label)
            object.__setattr__(self, side, values)
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def create(cls, obj: "Run | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class ProductLink:
    """A curation ``has_product``/``is_product`` edge between data entries.

    A label is unique per source entry across links; that constraint is
    enforced at the serving projection rather than on each record.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_product_link_v1",
        identity_name="core_product_link_v1",
        dedup="by_value",
        indexes=(("source_type", "source_id"), ("target_type", "target_id")),
    )

    source_type: str
    source_id: str
    target_type: str
    target_id: str
    label: str
    workflow_declaration_uri: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("source_type", "source_id", "target_type", "target_id", "label"):
            _validate_string(getattr(self, field_name), field_name)
        if (self.source_type, self.source_id) == (self.target_type, self.target_id):
            raise ValueError("ProductLink source and target must differ.")
        _validate_uri(self.workflow_declaration_uri, "workflow_declaration_uri")

    @classmethod
    def create(cls, obj: "ProductLink | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


class RunEntry:
    """Logical entry family for served :class:`Run` records.

    This family is not itself storable; store a ``Run`` directly.
    """

    type = "_httk_runs"
    definition_id = RUNS_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("RunEntry is a logical entry family; store a Run directly")


__all__ = ["RUNS_DEFINITION_ID", "ProductLink", "Run", "RunEdge", "RunEntry"]
