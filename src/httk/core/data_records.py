"""Stdlib-only records for one declared property value per entry."""

import datetime
import json
import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, fields
from typing import Annotated, Any, ClassVar, Self

from .definition_ids import AVERAGE_TOTAL_ENERGY, TOTAL_ENERGY
from .property_definitions import PropertyDefinition
from .provenance import RunEdge, _edges
from .register.schemas import load_property_definition
from .storage import IdentitySkip, Indexed, StorageInfo, StrongLink, Unique, stored_property
from .storage.stored_properties import QueryContext, QueryExpression, StoredPropertyProjection

RECORDS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/records"
TOTAL_ENERGY_DEFINITION_ID = TOTAL_ENERGY
AVERAGE_TOTAL_ENERGY_DEFINITION_ID = AVERAGE_TOTAL_ENERGY
_CANONICAL_JSON_ERROR = "value_json must be canonical JSON — use DataRecord.from_value."


def _validate_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string without surrounding whitespace.")


def _validate_timestamp(value: Any, field_name: str) -> None:
    if value is not None and (not isinstance(value, datetime.datetime) or value.utcoffset() is None):
        raise ValueError(f"Field '{field_name}' must be a timezone-aware datetime with an explicit offset.")


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value!r}")


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
    value = values.get("last_modified")
    if isinstance(value, str):
        try:
            value = datetime.datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 value for field 'last_modified': {value!r}.") from exc
        _validate_timestamp(value, "last_modified")
        values["last_modified"] = value
    elif value is not None:
        _validate_timestamp(value, "last_modified")
    return cls(**values)


def _validate_value_record(record: Any, string_fields: tuple[str, ...]) -> None:
    """Validate and normalize the fields shared by :class:`DataRecord` and :class:`DerivedDataRecord`."""
    for field_name in string_fields:
        _validate_string(getattr(record, field_name), field_name)
    if not isinstance(record.value_json, str) or not record.value_json:
        raise ValueError("Field 'value_json' must be a non-empty string.")
    try:
        value = json.loads(record.value_json, parse_constant=_reject_constant)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(_CANONICAL_JSON_ERROR) from exc
    if canonical != record.value_json:
        raise ValueError(_CANONICAL_JSON_ERROR)
    edges = _edges(record.product_of)
    labels: set[str] = set()
    for edge in edges:
        if edge.label in labels:
            raise ValueError(f"Duplicate label {edge.label!r} on {type(record).__name__} product_of.")
        labels.add(edge.label)
    object.__setattr__(record, "product_of", edges)
    _validate_timestamp(record.last_modified, "last_modified")


def _number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class DataRecord:
    """Store one canonical JSON value of one declared property.

    ``value_json`` is canonical JSON, with sorted object keys, compact
    separators, and no non-finite numeric values. ``value`` decodes it on
    access; ``value_number`` exposes finite numeric values for numeric queries.
    The human-readable and immutable identifiers and timestamp metadata are
    excluded from content identity.

    ``product_of`` names the entries this value describes, as
    :class:`~httk.core.storage.StrongLink` edges with the same
    :class:`~httk.core.provenance.RunEdge` scheme a :class:`~httk.core.Run` uses:
    string ``(label, entry_type, entry_id)`` triples, part of the record's content
    and therefore pinned to the exact entry revision. It is served forward as the
    ``product_of`` relationship and in reverse as ``has_product`` on the target,
    and is searchable through ``record.links.product_of`` and
    ``target.links.has_product``.

    :param definition_id: The property definition IRI for the value.
    :param name: The property name.
    :param value_json: The canonical JSON representation of the value.
    :param product_of: The entries this value is a product of, as labeled edges.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_data_record",
        identity_name="core_data_record",
        indexes=(("definition_id",), ("name",)),
    )

    definition_id: str
    name: str
    value_json: str
    product_of: Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")] = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "records"

    @property
    def value(self) -> Any:
        """Decode and return the stored property value."""
        return json.loads(self.value_json)

    @stored_property
    def value_number(self) -> float | None:
        """The decoded numeric value, stored as a numeric SQL query column."""
        return _number(self.value)

    def __post_init__(self) -> None:
        _validate_value_record(self, ("definition_id", "name"))

    @classmethod
    def from_value(
        cls,
        definition_id: str,
        name: str,
        value: Any,
        *,
        product_of: Iterable[RunEdge | Mapping[str, Any]] = (),
        id: str | None = None,
        immutable_id: str | None = None,
        last_modified: datetime.datetime | None = None,
    ) -> Self:
        """Encode a value canonically and construct its data record.

        :param definition_id: The property definition IRI for the value.
        :param name: The property name.
        :param value: The JSON value to encode.
        :param product_of: The entries this value is a product of, as labeled edges.
        :param id: The human-readable entry id shared by all revisions; minted by the store when None.
        :param immutable_id: The per-revision immutable id; minted by the store when None.
        :param last_modified: The optional timezone-aware metadata timestamp.
        :return: A data record containing the canonical JSON value.
        :raises TypeError: If the value contains an unsupported object.
        :raises ValueError: If the value is circular or contains a non-finite number, or if ``definition_id`` or ``name`` is invalid or ``last_modified`` is not timezone-aware.
        """
        return cls(
            definition_id,
            name,
            _canonical_json(value),
            product_of=_edges(product_of),
            id=id,
            immutable_id=immutable_id,
            last_modified=last_modified,
        )

    @classmethod
    def from_obj(cls, obj: "DataRecord | Mapping[str, Any]") -> Self:
        """Coerce a mapping or existing record into a :class:`DataRecord`.

        :param obj: A data record instance or field mapping.
        :return: The existing or newly constructed data record.
        :raises TypeError: If ``obj`` is neither a data record nor a mapping.
        :raises ValueError: If the mapping has unknown or invalid fields.
        """
        return _create(cls, obj)


@dataclass(frozen=True)
class DerivedDataRecord:
    """Store one canonical JSON value of a statistic or other derivation of a declared property.

    The sibling of :class:`DataRecord` for values such as the standard error or
    RMSE of a property: ``definition_id`` and ``name`` identify the BASE property
    (e.g. ``_httk_total_energy``) and ``derivation`` is the derivation-term IRI
    that qualifies it. ``derivation`` is part of the content identity, so two
    derivations of the same property never collide. Keeping derivations in their
    own record type leaves every existing :class:`DataRecord` identity unchanged.
    ``value_json``, ``value``, ``value_number`` and ``product_of`` behave as on
    :class:`DataRecord`.

    :param definition_id: The base property definition IRI.
    :param derivation: The derivation-term IRI qualifying the base property.
    :param name: The base property name.
    :param value_json: The canonical JSON representation of the derived value.
    :param product_of: The entries this value is a product of, as labeled edges.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_derived_data_record",
        identity_name="core_derived_data_record",
        indexes=(("definition_id",), ("derivation",), ("name",)),
    )

    definition_id: str
    derivation: str
    name: str
    value_json: str
    product_of: Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")] = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "records"

    @property
    def value(self) -> Any:
        """Decode and return the stored derived value."""
        return json.loads(self.value_json)

    @stored_property
    def value_number(self) -> float | None:
        """The decoded numeric value, stored as a numeric SQL query column."""
        return _number(self.value)

    def __post_init__(self) -> None:
        _validate_value_record(self, ("definition_id", "derivation", "name"))

    @classmethod
    def from_value(
        cls,
        definition_id: str,
        derivation: str,
        name: str,
        value: Any,
        *,
        product_of: Iterable[RunEdge | Mapping[str, Any]] = (),
        id: str | None = None,
        immutable_id: str | None = None,
        last_modified: datetime.datetime | None = None,
    ) -> Self:
        """Encode a derived value canonically and construct its record.

        :param definition_id: The base property definition IRI.
        :param derivation: The derivation-term IRI qualifying the base property.
        :param name: The base property name.
        :param value: The JSON value to encode.
        :param product_of: The entries this value is a product of, as labeled edges.
        :param id: The human-readable entry id shared by all revisions; minted by the store when None.
        :param immutable_id: The per-revision immutable id; minted by the store when None.
        :param last_modified: The optional timezone-aware metadata timestamp.
        :return: A derived data record containing the canonical JSON value.
        :raises TypeError: If the value contains an unsupported object.
        :raises ValueError: If the value is circular or contains a non-finite number, or if ``definition_id``, ``derivation`` or ``name`` is invalid or ``last_modified`` is not timezone-aware.
        """
        return cls(
            definition_id,
            derivation,
            name,
            _canonical_json(value),
            product_of=_edges(product_of),
            id=id,
            immutable_id=immutable_id,
            last_modified=last_modified,
        )

    @classmethod
    def from_obj(cls, obj: "DerivedDataRecord | Mapping[str, Any]") -> Self:
        """Coerce a mapping or existing record into a :class:`DerivedDataRecord`.

        :param obj: A derived data record instance or field mapping.
        :return: The existing or newly constructed derived data record.
        :raises TypeError: If ``obj`` is neither a derived data record nor a mapping.
        :raises ValueError: If the mapping has unknown or invalid fields.
        """
        return _create(cls, obj)


def _total_energy_query(context: QueryContext, operator: str, value: object) -> QueryExpression:
    field_ = context.field("total_energy")
    if operator == "IS_UNKNOWN":
        return context.is_null(field_)
    if operator == "IS_KNOWN":
        return context.not_(context.is_null(field_))
    return context.compare(field_, operator, context.constant(value))


class _TotalEnergyDefinitions(Mapping[str, PropertyDefinition]):
    """Served-name mapping resolved on first use; registry discovery runs after this module imports."""

    def __getitem__(self, key: str) -> PropertyDefinition:
        if key != "_httk_total_energy":
            raise KeyError(key)
        return load_property_definition(TOTAL_ENERGY_DEFINITION_ID).served_form()

    def __iter__(self) -> Iterator[str]:
        return iter(("_httk_total_energy",))

    def __len__(self) -> int:
        return 1


@dataclass(frozen=True)
class TotalEnergyRecord:
    """Store one total energy, in eV, as a typed record with a native float column.

    Unlike :class:`DataRecord`, the property is fixed by the class, so the
    ``_httk_total_energy`` value is served and queried from the ``total_energy``
    column. ``product_of`` has the same meaning as on :class:`DataRecord`.

    :param total_energy: The finite total energy in eV.
    :param product_of: The entries this value is a product of, as labeled edges.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises ValueError: If the energy is not a finite number or ``last_modified`` is not timezone-aware.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_total_energy", identity_name="core_total_energy"
    )
    __httk_property_definitions__: ClassVar[Mapping[str, PropertyDefinition]] = _TotalEnergyDefinitions()
    __httk_stored_properties__: ClassVar[Mapping[str, StoredPropertyProjection]] = {
        "_httk_total_energy": StoredPropertyProjection(
            response=lambda record: getattr(record, "total_energy"),  # noqa: B009
            query=_total_energy_query,
            sort=lambda context: context.field("total_energy"),
        )
    }

    total_energy: float
    product_of: Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")] = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "records"

    def __post_init__(self) -> None:
        if isinstance(self.total_energy, bool) or not isinstance(self.total_energy, (int, float)):
            raise ValueError("Field 'total_energy' must be a finite number.")
        object.__setattr__(self, "total_energy", float(self.total_energy))
        if not math.isfinite(self.total_energy):
            raise ValueError("Field 'total_energy' must be a finite number.")
        edges = _edges(self.product_of)
        if len({edge.label for edge in edges}) != len(edges):
            raise ValueError("Duplicate label on TotalEnergyRecord product_of.")
        object.__setattr__(self, "product_of", edges)
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def from_data_record(cls, record: DataRecord) -> Self:
        """Build a typed total-energy record from a generic data record.

        :param record: A data record whose definition is the total-energy property.
        :return: The typed record with the same value, edges and ids.
        :raises ValueError: If the record is for a different property definition or holds a non-numeric value.
        """
        if record.definition_id != TOTAL_ENERGY_DEFINITION_ID:
            raise ValueError(f"DataRecord definition {record.definition_id!r} is not {TOTAL_ENERGY_DEFINITION_ID!r}.")
        return cls(
            record.value,
            product_of=record.product_of,
            id=record.id,
            immutable_id=record.immutable_id,
            last_modified=record.last_modified,
        )


def _average_total_energy_query(context: QueryContext, operator: str, value: object) -> QueryExpression:
    field_ = context.field("average_total_energy")
    if operator == "IS_UNKNOWN":
        return context.is_null(field_)
    if operator == "IS_KNOWN":
        return context.not_(context.is_null(field_))
    return context.compare(field_, operator, context.constant(value))


class _AverageTotalEnergyDefinitions(Mapping[str, PropertyDefinition]):
    """Served-name mapping resolved on first use; registry discovery runs after this module imports."""

    def __getitem__(self, key: str) -> PropertyDefinition:
        if key != "_httk_average_total_energy":
            raise KeyError(key)
        return load_property_definition(AVERAGE_TOTAL_ENERGY_DEFINITION_ID).served_form()

    def __iter__(self) -> Iterator[str]:
        return iter(("_httk_average_total_energy",))

    def __len__(self) -> int:
        return 1


@dataclass(frozen=True)
class AverageTotalEnergyRecord:
    """Store one average total energy, in eV, as a typed record with a native float column.

    Unlike :class:`DataRecord`, the property is fixed by the class, so the
    ``_httk_average_total_energy`` value is served and queried from the ``average_total_energy``
    column. ``product_of`` has the same meaning as on :class:`DataRecord`.

    :param average_total_energy: The finite average total energy in eV.
    :param product_of: The entries this value is a product of, as labeled edges.
    :param id: The human-readable entry id shared by all revisions; minted by the store when None.
    :param immutable_id: The per-revision immutable id; minted by the store when None.
    :param last_modified: The optional timezone-aware metadata timestamp.
    :raises ValueError: If the energy is not a finite number or ``last_modified`` is not timezone-aware.
    """

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_average_total_energy", identity_name="core_average_total_energy"
    )
    __httk_property_definitions__: ClassVar[Mapping[str, PropertyDefinition]] = _AverageTotalEnergyDefinitions()
    __httk_stored_properties__: ClassVar[Mapping[str, StoredPropertyProjection]] = {
        "_httk_average_total_energy": StoredPropertyProjection(
            response=lambda record: getattr(record, "average_total_energy"),  # noqa: B009
            query=_average_total_energy_query,
            sort=lambda context: context.field("average_total_energy"),
        )
    }

    average_total_energy: float
    product_of: Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")] = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "records"

    def __post_init__(self) -> None:
        if isinstance(self.average_total_energy, bool) or not isinstance(self.average_total_energy, (int, float)):
            raise ValueError("Field 'average_total_energy' must be a finite number.")
        object.__setattr__(self, "average_total_energy", float(self.average_total_energy))
        if not math.isfinite(self.average_total_energy):
            raise ValueError("Field 'average_total_energy' must be a finite number.")
        edges = _edges(self.product_of)
        if len({edge.label for edge in edges}) != len(edges):
            raise ValueError("Duplicate label on AverageTotalEnergyRecord product_of.")
        object.__setattr__(self, "product_of", edges)
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def from_data_record(cls, record: DataRecord) -> Self:
        """Build a typed average-total-energy record from a generic data record.

        :param record: A data record whose definition is the average-total-energy property.
        :return: The typed record with the same value, edges and ids.
        :raises ValueError: If the record is for a different property definition or holds a non-numeric value.
        """
        if record.definition_id != AVERAGE_TOTAL_ENERGY_DEFINITION_ID:
            raise ValueError(
                f"DataRecord definition {record.definition_id!r} is not {AVERAGE_TOTAL_ENERGY_DEFINITION_ID!r}."
            )
        return cls(
            record.value,
            product_of=record.product_of,
            id=record.id,
            immutable_id=record.immutable_id,
            last_modified=record.last_modified,
        )


class DataRecordEntry:
    """Logical entry family for served :class:`DataRecord` records.

    This family is not itself storable; store a ``DataRecord`` directly.
    """

    type = "records"
    definition_id = RECORDS_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("DataRecordEntry is a logical entry family; store a DataRecord directly")


__all__ = [
    "AVERAGE_TOTAL_ENERGY_DEFINITION_ID",
    "RECORDS_DEFINITION_ID",
    "TOTAL_ENERGY_DEFINITION_ID",
    "AverageTotalEnergyRecord",
    "DataRecord",
    "DataRecordEntry",
    "DerivedDataRecord",
    "TotalEnergyRecord",
]
