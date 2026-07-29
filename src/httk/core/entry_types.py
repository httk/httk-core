#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Data models for the standard OPTIMADE entry types.

This module holds light frozen dataclasses that carry one record's worth of
data for each of httk-core's vendored OPTIMADE standards (``references``,
``files``, ``calculations``):

- :class:`Reference`, :class:`File`, :class:`Calculation` — one immutable
  record each, with a field for every non-core property of the respective
  standard (``id`` comes from a provider's mapping key; ``type`` is constant).

These are the neutral top-level record models. The
:class:`~httk.core.EntryProvider` implementations that serve them through the
provider contract live in the *httk-data* module (``httk.data.entry_providers``),
which imports these dataclasses; httk-core keeps only the stdlib-only models.
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any, Self


@dataclass(frozen=True)
class Reference:
    """One OPTIMADE ``references`` record (a bibliographic reference).

    Every field is optional and defaults to ``None``; ``id`` is supplied by the
    provider's mapping key and ``type`` is the constant ``"references"``.
    ``last_modified`` is a timezone-aware ``datetime`` value. Serving layers
    emit timestamps with ``datetime.isoformat()``, including their offset.
    Author and editor lists are tuples of plain name dictionaries.
    """

    immutable_id: str | None = None
    last_modified: datetime.datetime | None = None
    address: str | None = None
    annote: str | None = None
    booktitle: str | None = None
    chapter: str | None = None
    crossref: str | None = None
    edition: str | None = None
    howpublished: str | None = None
    institution: str | None = None
    journal: str | None = None
    key: str | None = None
    month: str | None = None
    note: str | None = None
    number: str | None = None
    organization: str | None = None
    pages: str | None = None
    publisher: str | None = None
    school: str | None = None
    series: str | None = None
    title: str | None = None
    volume: str | None = None
    year: str | None = None
    bib_type: str | None = None
    authors: tuple[Mapping[str, Any], ...] | None = None
    editors: tuple[Mapping[str, Any], ...] | None = None
    doi: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def create(cls, obj: "Reference | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class File:
    """One OPTIMADE ``files`` record.

    ``url`` and ``name`` are required; all other fields default to ``None``.
    ``id`` is supplied by the provider's mapping key and ``type`` is the
    constant ``"files"``. Timestamps are timezone-aware ``datetime`` values;
    serving layers emit them with ``datetime.isoformat()``, including their
    offset. ``checksums`` is a mapping of algorithm name to hex digest.
    """

    url: str
    name: str
    immutable_id: str | None = None
    last_modified: datetime.datetime | None = None
    url_stable_until: datetime.datetime | None = None
    size: int | None = None
    media_type: str | None = None
    version: str | None = None
    modification_timestamp: datetime.datetime | None = None
    description: str | None = None
    checksums: Mapping[str, str] | None = None
    atime: datetime.datetime | None = None
    ctime: datetime.datetime | None = None
    mtime: datetime.datetime | None = None

    def __post_init__(self) -> None:
        for field in _FILE_TIMESTAMP_FIELDS:
            _validate_timestamp(getattr(self, field), field)

    @classmethod
    def create(cls, obj: "File | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class Calculation:
    """One OPTIMADE ``calculations`` record.

    Every field is optional and defaults to ``None``; ``id`` is supplied by the
    provider's mapping key and ``type`` is the constant ``"calculations"``.
    ``last_modified`` is a timezone-aware ``datetime`` value; serving layers
    emit it with ``datetime.isoformat()``, including its offset. The standard
    ``calculations`` entry type carries only the shared core properties;
    database-specific results are added by extending the definition.
    """

    immutable_id: str | None = None
    last_modified: datetime.datetime | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.last_modified, "last_modified")

    @classmethod
    def create(cls, obj: "Calculation | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


_TIMESTAMP_FIELDS = frozenset(
    {
        "last_modified",
        "atime",
        "ctime",
        "mtime",
        "modification_timestamp",
        "url_stable_until",
    }
)
_FILE_TIMESTAMP_FIELDS = (
    "last_modified",
    "url_stable_until",
    "modification_timestamp",
    "atime",
    "ctime",
    "mtime",
)


def _validate_timestamp(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, datetime.datetime) or value.tzinfo is None):
        raise ValueError(f"Field '{field}' must be a timezone-aware datetime with an explicit offset.")


def _create(cls: type[Any], obj: Any) -> Any:
    """Coerce ``obj`` (an instance or a plain mapping) into ``cls``."""
    if isinstance(obj, cls):
        return obj
    if isinstance(obj, Mapping):
        known = {f.name for f in fields(cls)}
        unknown = [key for key in obj if key not in known]
        if unknown:
            raise ValueError("Unknown field(s) for " + cls.__name__ + ": " + ", ".join(sorted(unknown)) + ".")
        values = dict(obj)
        for field in _TIMESTAMP_FIELDS & known:
            value = values.get(field)
            if isinstance(value, str):
                try:
                    parsed = datetime.datetime.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(f"Invalid ISO-8601 value for field '{field}': {value!r}.") from exc
                _validate_timestamp(parsed, field)
                values[field] = parsed
            elif value is not None:
                _validate_timestamp(value, field)
        return cls(**values)
    raise TypeError("Expected a " + cls.__name__ + " or a mapping, got " + type(obj).__name__ + ".")
