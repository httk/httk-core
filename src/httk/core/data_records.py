"""Stdlib-only records for one declared property value per entry."""

import datetime
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Annotated, Any, ClassVar, Self

from .storage import IdentitySkip, StorageInfo, content_id, stored_property

RECORDS_DEFINITION_ID = "https://schemas.httk.org/defs/v0.1/entrytypes/records"
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


@dataclass(frozen=True)
class DataRecord:
    """One canonical JSON value of one declared property."""

    __httk_storage__: ClassVar[StorageInfo] = StorageInfo(
        storage_name="core_data_record_v1",
        identity_name="core_data_record_v1",
        indexes=(("definition_id",), ("name",)),
    )

    definition_id: str
    name: str
    value_json: str
    immutable_id: Annotated[str | None, IdentitySkip()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)

    @property
    def type(self) -> str:
        return "_httk_records"

    @property
    def id(self) -> str:
        return content_id(self)

    @property
    def value(self) -> Any:
        return json.loads(self.value_json)

    @stored_property
    def value_number(self) -> float | None:
        """The decoded numeric value, stored as a numeric SQL query column."""
        value = self.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        try:
            result = float(value)
        except OverflowError:
            return None
        return result if math.isfinite(result) else None

    def __post_init__(self) -> None:
        for field_name in ("definition_id", "name"):
            _validate_string(getattr(self, field_name), field_name)
        if not isinstance(self.value_json, str) or not self.value_json:
            raise ValueError("Field 'value_json' must be a non-empty string.")
        try:
            value = json.loads(self.value_json, parse_constant=_reject_constant)
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(_CANONICAL_JSON_ERROR) from exc
        if canonical != self.value_json:
            raise ValueError(_CANONICAL_JSON_ERROR)
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def from_value(
        cls,
        definition_id: str,
        name: str,
        value: Any,
        *,
        immutable_id: str | None = None,
        last_modified: datetime.datetime | None = None,
    ) -> Self:
        return cls(
            definition_id,
            name,
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False),
            immutable_id=immutable_id,
            last_modified=last_modified,
        )

    @classmethod
    def create(cls, obj: "DataRecord | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


class DataRecordEntry:
    """Logical entry family for served :class:`DataRecord` records.

    This family is not itself storable; store a ``DataRecord`` directly.
    """

    type = "_httk_records"
    definition_id = RECORDS_DEFINITION_ID

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        raise TypeError("DataRecordEntry is a logical entry family; store a DataRecord directly")


__all__ = ["RECORDS_DEFINITION_ID", "DataRecord", "DataRecordEntry"]
