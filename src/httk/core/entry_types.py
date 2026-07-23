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

"""Data models and entry providers for the standard OPTIMADE entry types.

This module pairs httk-core's vendored OPTIMADE standards (``references``,
``files``, ``calculations``) with light frozen dataclasses that hold one
record's worth of data, and with :class:`~httk.core.EntryProvider`
implementations serving them:

- :class:`Reference`, :class:`File`, :class:`Calculation` — one immutable
  record each, with a field for every non-core property of the respective
  standard (``id`` comes from the provider's mapping key; ``type`` is constant).
- :class:`ReferenceEntryProvider`, :class:`FileEntryProvider`,
  :class:`CalculationEntryProvider` — providers mapping ``{id: record}`` to the
  neutral entry-provider contract, describing each entry type with its vendored
  :class:`~httk.core.property_definitions.EntryTypeDefinition`.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from typing import Any, Self

from .entry_provider import EntryProvider
from .property_definitions import EntryTypeDefinition, standard_entry_type


@dataclass(frozen=True)
class Reference:
    """One OPTIMADE ``references`` record (a bibliographic reference).

    Every field is optional and defaults to ``None``; ``id`` is supplied by the
    provider's mapping key and ``type`` is the constant ``"references"``. Author
    and editor lists are tuples of plain name dictionaries.
    """

    immutable_id: str | None = None
    last_modified: str | None = None
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

    @classmethod
    def create(cls, obj: "Reference | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class File:
    """One OPTIMADE ``files`` record.

    Every field is optional and defaults to ``None``; ``id`` is supplied by the
    provider's mapping key and ``type`` is the constant ``"files"``. Timestamps
    are ISO-8601 strings and ``checksums`` is a mapping of algorithm name to hex
    digest.
    """

    immutable_id: str | None = None
    last_modified: str | None = None
    url: str | None = None
    url_stable_until: str | None = None
    name: str | None = None
    size: int | None = None
    media_type: str | None = None
    version: str | None = None
    modification_timestamp: str | None = None
    description: str | None = None
    checksums: Mapping[str, str] | None = None
    atime: str | None = None
    ctime: str | None = None
    mtime: str | None = None

    @classmethod
    def create(cls, obj: "File | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


@dataclass(frozen=True)
class Calculation:
    """One OPTIMADE ``calculations`` record.

    Every field is optional and defaults to ``None``; ``id`` is supplied by the
    provider's mapping key and ``type`` is the constant ``"calculations"``. The
    standard ``calculations`` entry type carries only the shared core
    properties; database-specific results are added by extending the definition.
    """

    immutable_id: str | None = None
    last_modified: str | None = None

    @classmethod
    def create(cls, obj: "Calculation | Mapping[str, Any]") -> Self:
        return _create(cls, obj)


def _create(cls: type[Any], obj: Any) -> Any:
    """Coerce ``obj`` (an instance or a plain mapping) into ``cls``."""
    if isinstance(obj, cls):
        return obj
    if isinstance(obj, Mapping):
        known = {f.name for f in fields(cls)}
        unknown = [key for key in obj if key not in known]
        if unknown:
            raise ValueError("Unknown field(s) for " + cls.__name__ + ": " + ", ".join(sorted(unknown)) + ".")
        return cls(**obj)
    raise TypeError("Expected a " + cls.__name__ + " or a mapping, got " + type(obj).__name__ + ".")


def _provider_columns(record_type: type[Any]) -> dict[str, str]:
    """The served-property to record-column map for a standard entry type."""
    columns = {"id": "__id", "type": "type"}
    columns.update({field.name: field.name for field in fields(record_type)})
    return columns


def _provider_records(entry_type: str, record_type: type[Any], entries: Mapping[str, Any]) -> list[dict[str, Any]]:
    """JSON-able records for a standard entry type, one per stored instance."""
    field_names = [field.name for field in fields(record_type)]
    records: list[dict[str, Any]] = []
    for entry_id, record in entries.items():
        row: dict[str, Any] = {"__id": entry_id, "type": entry_type}
        for name in field_names:
            row[name] = getattr(record, name)
        records.append(row)
    return records


class ReferenceEntryProvider(EntryProvider):
    """Serves OPTIMADE ``references`` from a mapping of id to :class:`Reference`."""

    def __init__(self, entries: Mapping[str, "Reference | Mapping[str, Any]"]) -> None:
        self._entries: dict[str, Reference] = {str(key): Reference.create(value) for key, value in entries.items()}

    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        return {"references": standard_entry_type("references")}

    def columns(self, entry_type: str) -> Mapping[str, str]:
        if entry_type != "references":
            raise KeyError("ReferenceEntryProvider serves only the 'references' entry type.")
        return _provider_columns(Reference)

    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        if entry_type != "references":
            raise KeyError("ReferenceEntryProvider serves only the 'references' entry type.")
        return _provider_records("references", Reference, self._entries)


class FileEntryProvider(EntryProvider):
    """Serves OPTIMADE ``files`` from a mapping of id to :class:`File`."""

    def __init__(self, entries: Mapping[str, "File | Mapping[str, Any]"]) -> None:
        self._entries: dict[str, File] = {str(key): File.create(value) for key, value in entries.items()}

    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        return {"files": standard_entry_type("files")}

    def columns(self, entry_type: str) -> Mapping[str, str]:
        if entry_type != "files":
            raise KeyError("FileEntryProvider serves only the 'files' entry type.")
        return _provider_columns(File)

    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        if entry_type != "files":
            raise KeyError("FileEntryProvider serves only the 'files' entry type.")
        return _provider_records("files", File, self._entries)


class CalculationEntryProvider(EntryProvider):
    """Serves OPTIMADE ``calculations`` from a mapping of id to :class:`Calculation`."""

    def __init__(self, entries: Mapping[str, "Calculation | Mapping[str, Any]"]) -> None:
        self._entries: dict[str, Calculation] = {str(key): Calculation.create(value) for key, value in entries.items()}

    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        return {"calculations": standard_entry_type("calculations")}

    def columns(self, entry_type: str) -> Mapping[str, str]:
        if entry_type != "calculations":
            raise KeyError("CalculationEntryProvider serves only the 'calculations' entry type.")
        return _provider_columns(Calculation)

    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        if entry_type != "calculations":
            raise KeyError("CalculationEntryProvider serves only the 'calculations' entry type.")
        return _provider_records("calculations", Calculation, self._entries)
