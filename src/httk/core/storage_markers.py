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

"""Stdlib-only marker vocabulary for declaring storable record classes.

A *storable* class is a plain frozen dataclass whose fields a storage layer
(such as the database layer in *httk-data*) can resolve into a relational
schema. Storability is non-intrusive: there is no base class to inherit.
This module holds only the declaration vocabulary — the markers attached to
fields via :class:`typing.Annotated`, the optional class-level
:class:`StorageInfo` declaration, and the :class:`stored_property` decorator
for derived, queryable properties — so that any httk module (or application)
can declare storable classes while depending only on httk-core. All schema
resolution and storage work happens in the storage layer.

Markers are used like this::

    @dataclass(frozen=True)
    class StructureRecord:
        __httk_storage__: ClassVar[StorageInfo] = StorageInfo(indexes=(("spacegroup", "formula"),))

        formula: Annotated[str, Indexed()]
        spacegroup: int
        cell_basis: Annotated[FracVector, Shape(3, 3)]
        symbols: list[str]

        @stored_property
        def natoms(self) -> int:
            return len(self.symbols)

The class-level declaration is optional; a storage layer must accept plain
frozen dataclasses with no markers at all, and may also accept an external
:class:`StorageInfo` override for classes that cannot be modified.
"""

from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "Indexed",
    "Unique",
    "Skip",
    "Shape",
    "DedupPolicy",
    "StorageInfo",
    "STORAGE_INFO_ATTRIBUTE",
    "stored_property",
]

STORAGE_INFO_ATTRIBUTE: Final = "__httk_storage__"
"""Class attribute name where a storable class may attach its :class:`StorageInfo`."""

type DedupPolicy = Literal["content_id", "by_value", "none"]
"""How a storage layer deduplicates saved instances of a class.

- ``"content_id"``: reuse an existing row whose stored content identity matches
  (the default; suited to immutable value objects).
- ``"by_value"``: reuse an existing row whose stored columns all match (suited
  to join-objects such as tags and references, whose identity is their value).
- ``"none"``: always insert a new row.
"""

_DEDUP_POLICIES: Final = ("content_id", "by_value", "none")


@dataclass(frozen=True)
class Indexed:
    """Field marker: request a single-column index on this field's column(s)."""


@dataclass(frozen=True)
class Unique:
    """Field marker: request a unique index on this field's column(s)."""


@dataclass(frozen=True)
class Skip:
    """Field marker: the field exists on the dataclass but is not stored."""


@dataclass(frozen=True)
class Shape:
    """Field marker: fixed or variable shape for a vector-valued field.

    ``rows >= 1`` declares a fixed-shape value stored inline (flattened
    row-major into columns). ``rows == 0`` declares a variable number of rows
    with ``cols`` fixed columns each, stored out-of-line (one row per entry,
    in insertion order).

    Args:
        rows: Number of rows; ``0`` means variable-length.
        cols: Number of columns per row; must be at least ``1``.
    """

    rows: int
    cols: int = 1

    def __post_init__(self) -> None:
        if self.rows < 0:
            raise ValueError(f"Shape rows must be >= 0 (0 means variable-length), got {self.rows}")
        if self.cols < 1:
            raise ValueError(f"Shape cols must be >= 1, got {self.cols}")


@dataclass(frozen=True)
class StorageInfo:
    """Optional class-level storage declaration for a storable dataclass.

    Attach as the class attribute named by :data:`STORAGE_INFO_ATTRIBUTE`
    (``__httk_storage__``), annotated ``ClassVar[StorageInfo]`` so dataclass
    processing ignores it. A storage layer may also accept an instance as an
    external override for classes that cannot be modified.

    Args:
        table_name: Storage table name; ``None`` derives one from the class name.
        indexes: Composite indexes, each a tuple of field names.
        dedup: Deduplication policy applied when saving; see :data:`DedupPolicy`.
    """

    table_name: str | None = None
    indexes: tuple[tuple[str, ...], ...] = ()
    dedup: DedupPolicy = "content_id"

    def __post_init__(self) -> None:
        if self.dedup not in _DEDUP_POLICIES:
            raise ValueError(f"StorageInfo dedup must be one of {_DEDUP_POLICIES}, got {self.dedup!r}")
        for index in self.indexes:
            if not index:
                raise ValueError("StorageInfo indexes must not contain empty field-name tuples")


class stored_property(property):
    """A derived property that a storage layer stores and makes queryable.

    Use exactly like :class:`property` (getter only). The value type is read
    from the getter's return annotation. On save, the storage layer evaluates
    and stores the value alongside the declared fields; on load, the value is
    recomputed by the property rather than passed to ``__init__``.
    """
