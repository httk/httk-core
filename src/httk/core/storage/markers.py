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
(such as the database layer in *httk-store*) can resolve into a relational
schema. Storability is non-intrusive: there is no base class to inherit.
This module holds only the declaration vocabulary — the markers attached to
fields via :class:`typing.Annotated`, the optional class-level
:class:`StorageInfo` declaration, and the :class:`stored_property` decorator
for derived, queryable properties — so that any httk module (or application)
can declare storable classes while depending only on httk-core. All schema
resolution and storage work happens in the storage layer.

Storage may optionally call a record class's ``__httk_validate__`` classmethod
when saving a record instance; implementations may raise to reject invalid data.

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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Literal

__all__ = [
    "STORAGE_INFO_ATTRIBUTE",
    "DedupPolicy",
    "IdentitySkip",
    "Indexed",
    "Related",
    "Shape",
    "Skip",
    "StorageInfo",
    "Unique",
    "WeakLink",
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

Values equal across ``int`` and ``Fraction`` can hash differently, while
``Decimal`` and ``Fraction`` unify; naive and aware datetimes are distinct.
Records combining those sources may therefore not deduplicate.
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
class IdentitySkip:
    """Field marker: exclude the field from content identity."""


@dataclass(frozen=True)
class Shape:
    """Field marker: fixed or variable shape for a vector-valued field.

    ``rows >= 1`` declares a fixed-shape value stored inline (flattened
    row-major into columns). ``rows == 0`` declares a variable number of rows
    with ``cols`` fixed columns each, stored out-of-line (one row per entry,
    in insertion order).

    :param rows: Number of rows; ``0`` means variable-length.
    :param cols: Number of columns per row; must be at least ``1``.
    :raises ValueError: If ``rows`` is negative or ``cols`` is less than ``1``.
    """

    rows: int
    cols: int = 1

    def __post_init__(self) -> None:
        if self.rows < 0:
            raise ValueError(f"Shape rows must be >= 0 (0 means variable-length), got {self.rows}")
        if self.cols < 1:
            raise ValueError(f"Shape cols must be >= 1, got {self.cols}")


@dataclass(frozen=True)
class Related:
    """Field marker: relationship metadata for a reference or list-of-storable field.

    Applies to a field holding another storable class (a *reference* field) or
    a ``list``/``tuple`` of storable classes. When the field's target class is
    served alongside the declaring class, the storage layer surfaces the field
    as a relationship; this marker attaches the OPTIMADE per-identifier
    metadata that flows into each emitted
    :class:`~httk.core.entry_provider.RelatedEntry` — ``role`` (machine
    readable, OPTIMADE v1.3 ``meta.role``) and ``description`` (human readable,
    OPTIMADE v1.2 ``meta.description``). ``serve=False`` suppresses the field
    as a relationship entirely.

    :param role: The machine-readable relationship role, if any.
    :param description: The human-readable relationship description, if any.
    :param serve: Whether the field is served as a relationship at all.
    """

    role: str | None = None
    description: str | None = None
    serve: bool = True


@dataclass(frozen=True)
class WeakLink:
    """Class-level declaration of a store-managed, lineage-level link to another storable class.

    Declared in :attr:`StorageInfo.links` on the *source* class (links are
    directed). A weak link is a store-managed association living in a dedicated
    link table, not in any record field: it binds *lineages*, associating this
    record's logical id with a ``target`` record's logical id, and both
    endpoints always resolve to the *latest* revision on their respective side
    (this is what makes the link *weak*, in contrast to sid-pinned reference and
    child fields). Link rows are themselves append-only lineages — they are
    revisable, retractable, and ``as_of``-aware — and are set-valued: a source
    lineage may link many targets under the same declaration. Because links are
    not part of a record's value, they do **not** participate in content
    identity; adding or retracting a link never changes the record's
    ``content_id``.

    Only links declared ``exposed_relationship=True`` are served through the
    OPTIMADE relationship facility; ``role`` and ``description`` carry the same
    per-identifier OPTIMADE metadata as :class:`Related` into each served
    relationship. ``target`` is the storable frozen dataclass this link points
    at; only that it is a class is checked here, as deep storability validation
    is performed by the storage layer.

    :param name: The link name; must be a valid Python identifier. Namespaces the link (e.g. accessed as ``record.links.<name>``).
    :param target: The storable class this link points at.
    :param exposed_relationship: Whether the link is served through the OPTIMADE relationship facility.
    :param role: The machine-readable relationship role, if any.
    :param description: The human-readable relationship description, if any.
    :raises ValueError: If ``name`` is not a valid Python identifier.
    :raises TypeError: If ``target`` is not a class.
    """

    name: str
    target: type
    exposed_relationship: bool = False
    role: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.isidentifier():
            raise ValueError(f"WeakLink name must be a valid Python identifier, got {self.name!r}")
        if not isinstance(self.target, type):
            raise TypeError(f"WeakLink target must be a class, got {self.target!r}")


@dataclass(frozen=True)
class StorageInfo:
    """Optional class-level storage declaration for a storable dataclass.

    Attach as the class attribute named by
    :data:`~httk.core.storage.markers.STORAGE_INFO_ATTRIBUTE`
    (``__httk_storage__``), annotated ``ClassVar[StorageInfo]`` so dataclass
    processing ignores it. A storage layer may also accept an instance as an
    external override for classes that cannot be modified.

    :param storage_name: The physical storage name; ``None`` derives one from the class name. Relational backends use it as the table name, and document stores use it as the collection name.
    :param indexes: Composite indexes, each a tuple of field names.
    :param dedup: The deduplication policy applied when saving; see :data:`~httk.core.storage.markers.DedupPolicy`.
    :param links: Class-level weak-link declarations; see :class:`~httk.core.storage.markers.WeakLink`.
    :param identity_name: The logical name included in content identity; ``None`` derives it from the declaring class and its bases.
    :raises ValueError: If ``dedup`` or an identity name or index declaration is invalid.
    """

    storage_name: str | None = None
    indexes: tuple[tuple[str, ...], ...] = ()
    dedup: DedupPolicy = "content_id"
    links: tuple[WeakLink, ...] = ()
    identity_name: str | None = None

    def __post_init__(self) -> None:
        if self.dedup not in _DEDUP_POLICIES:
            raise ValueError(f"StorageInfo dedup must be one of {_DEDUP_POLICIES}, got {self.dedup!r}")
        if self.identity_name is not None and (
            not isinstance(self.identity_name, str)
            or not self.identity_name.strip()
            or self.identity_name != self.identity_name.strip()
        ):
            raise ValueError(
                "StorageInfo identity_name must be a nonempty string without surrounding whitespace or None"
            )
        for index in self.indexes:
            if not index:
                raise ValueError("StorageInfo indexes must not contain empty field-name tuples")


class stored_property(property):
    """A derived property that a storage layer stores and makes queryable.

    Use exactly like :class:`property` (getter only). The value type is read
    from the getter's return annotation. On save, the storage layer evaluates
    and stores the value alongside the declared fields; on load, the value is
    recomputed by the property rather than passed to ``__init__``. The getter
    must declare a return annotation when the property is created.

    :param fget: The getter function whose derived value is stored.
    :param fset: An optional setter, normally unused by storage declarations.
    :param fdel: An optional deleter, normally unused by storage declarations.
    :param doc: An optional property documentation string.
    :raises TypeError: If ``fget`` has no return annotation.
    """

    def __init__(
        self,
        fget: Callable[..., Any] | None = None,
        fset: Callable[..., Any] | None = None,
        fdel: Callable[..., Any] | None = None,
        doc: str | None = None,
    ) -> None:
        if fget is not None and "return" not in getattr(fget, "__annotations__", {}):
            raise TypeError("stored_property getter needs a return annotation")
        super().__init__(fget, fset, fdel, doc)
