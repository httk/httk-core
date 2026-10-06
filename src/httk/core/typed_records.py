"""Storage layouts of typed result records, derived from OPTIMADE property definitions.

A typed result record stores the value of one property definition as plain fields. :func:`member_layout`
derives those fields: one per member of a dictionary-typed definition (in document order), or a single
field named after the definition for a scalar or list definition.

**Flattened storage rule.** A scalar member is stored as-is. A list-valued member of any depth, with fixed
or variable sizes, is stored as *one* flat ``tuple`` of its leaves in row-major order; the nested value is
reassembled from the definition's ``x-optimade-dimensions``. Fixed sizes come from the definition. A
variable outermost size comes from a sibling member whose outermost dimension has the same name, else from
the flat length divided by the product of the inner sizes. A variable inner size must be supplied by such a
sibling, so it cannot be reconstructed from nothing; a layout that would need one is rejected.

**Runtime.** A typed record class is a frozen dataclass deriving from :class:`TypedRecord` whose
``__httk_typed_record__`` :class:`TypedRecordSpec` names the definition. Its value fields follow the
layout (required members first, then non-required members), followed by the standard ``product_of``,
``id``, ``immutable_id`` and ``last_modified`` fields. :meth:`TypedRecordSpec.projections` serves and
queries the value from those fields.
"""

import datetime
import keyword
import math
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, fields
from functools import cached_property
from typing import Any, ClassVar, Self, cast

from .data_records import DataRecord, _validate_string, _validate_timestamp
from .property_definitions import _HTTK_DEFS_BASE, PropertyDefinition
from .provenance import RunEdge, _edges
from .register.schemas import load_property_definition
from .storage.stored_properties import (
    QueryContext,
    QueryExpression,
    QueryLiteralError,
    StoredPropertyProjection,
)

__all__ = ["MemberLayout", "TypedRecord", "TypedRecordSpec", "member_layout"]

_LEAVES = frozenset({"float", "integer", "string", "boolean"})
# Must contain the store's reserved field names (httk-store backend/schema.py, pinned by a store test).
_RESERVED_FIELDS = frozenset(
    {
        "_httk_role",
        "alt_id",
        "alt_kind",
        "links",
        "logical_id",
        "store_timestamp",
        "type",
        "value",
        "definition_id",
        "derivation",
        "id",
        "immutable_id",
        "last_modified",
        "product_of",
        "sid",
        "content_id",
    }
)


@dataclass(frozen=True, slots=True)
class MemberLayout:
    """How one member of a property definition's value is stored in a typed record.

    :param field: The record field name: ``"_".join(path)``, or the definition name for a non-dictionary
        definition.
    :param path: The member path within the value; ``()`` for a scalar or list definition's own value.
    :param fulltype: The compact fulltype, e.g. ``"float"`` or ``"list of list of float"``.
    :param leaf: The scalar leaf type: ``"float"``, ``"integer"``, ``"string"`` or ``"boolean"``.
    :param required: Whether the member is a required dictionary member (always true for a non-dictionary
        definition's value).
    :param nullable: Whether the member or value itself may be null.
    :param element_nullable: Whether list leaf items may be null (false for scalars).
    :param dimensions: The ``(name, size)`` of every list level, outermost first; ``size`` is ``None`` for a
        variable dimension. Empty for scalars.
    """

    field: str
    path: tuple[str, ...]
    fulltype: str
    leaf: str
    required: bool
    nullable: bool
    element_nullable: bool
    dimensions: tuple[tuple[str, int | None], ...]


def _lower_first(text: str) -> str:
    """Lower-case the first letter of *text* unless it starts an acronym (first two characters upper-case).

    :param text: A title.
    :return: The title for use mid-sentence.
    """
    return text if text[:2].isupper() else text[:1].lower() + text[1:]


def _nullable(level: Mapping[str, Any]) -> bool:
    json_type = level.get("type")
    return isinstance(json_type, list) and "null" in json_type


def _layout_one(
    definition: str, field: str, path: tuple[str, ...], level: Mapping[str, Any], required: bool
) -> MemberLayout:
    where = f"{definition}: member {'.'.join(path) or field!r}"
    levels: list[Mapping[str, Any]] = []
    leaf = level
    while leaf.get("x-optimade-type") == "list":
        levels.append(leaf)
        leaf = leaf.get("items", {})
    kind = leaf.get("x-optimade-type")
    if kind == "dictionary":
        raise ValueError(
            f"{where} is a {'list of dictionaries' if levels else 'nested dictionary'}, which typed records do not support"
        )
    if kind not in _LEAVES:
        raise ValueError(f"{where} has leaf type {kind!r}; typed records support only {sorted(_LEAVES)}")
    if any(_nullable(inner) for inner in levels[1:]):
        raise ValueError(f"{where} has a nullable inner list level, which a flat tuple cannot store")
    # Mirror _check_level: names[i]/sizes[i] declared at list level j describe list level j + i.
    declared: list[list[tuple[str | None, int | None]]] = [[] for _ in levels]
    for depth, list_level in enumerate(levels):
        dims = list_level.get("x-optimade-dimensions") or {}
        names, sizes = dims.get("names") or [], dims.get("sizes") or []
        for offset in range(max(len(names), len(sizes))):
            if depth + offset < len(levels):
                declared[depth + offset].append(
                    (names[offset] if offset < len(names) else None, sizes[offset] if offset < len(sizes) else None)
                )
    dimensions: list[tuple[str, int | None]] = []
    for depth, entries in enumerate(declared):
        names_found = {name for name, _ in entries if name is not None}
        sizes_found = {size for _, size in entries if size is not None}
        if len(names_found) != 1 or len(sizes_found) > 1:
            raise ValueError(f"{where} list level {depth} needs exactly one dimension declaration, found {entries!r}")
        dimensions.append((names_found.pop(), sizes_found.pop() if sizes_found else None))
    return MemberLayout(
        field=field,
        path=path,
        fulltype="list of " * len(levels) + kind,
        leaf=kind,
        required=required,
        nullable=_nullable(level),
        element_nullable=bool(levels) and _nullable(leaf),
        dimensions=tuple(dimensions),
    )


def member_layout(definition: PropertyDefinition) -> tuple[MemberLayout, ...]:
    """Derive the typed-record storage layout of *definition*.

    A dictionary definition gives one layout per member in document order; any other definition gives a
    single layout for its own value, with ``path == ()``. The derivation is deterministic and shared by the
    record generator and the runtime. A top-level value is never stored as null, even when the definition
    is nullable (a typed record always holds a value); ``nullable`` then only describes the definition.

    :param definition: The property definition to lay out.
    :return: The member layouts.
    :raises ValueError: Naming the definition and member, for a timestamp or other unsupported leaf, a nested
        dictionary or list of dictionaries, a nullable inner list level, a list level without exactly one dimension declaration, a
        variable inner dimension no sibling's outermost dimension supplies (any variable inner dimension of
        a non-dictionary definition), or a reserved or colliding field name.
    """
    document = definition.as_optimade()
    name = definition.name
    if document.get("x-optimade-type") == "dictionary":
        required = set(document.get("required", ()))
        layouts = tuple(
            _layout_one(name, key, (key,), member, key in required)
            for key, member in document.get("properties", {}).items()
        )
    else:
        layouts = (_layout_one(name, name, (), document, True),)
    fields = {layout.field for layout in layouts}
    for layout in layouts:
        field = layout.field
        derived = {other + suffix for other in fields - {field} for suffix in ("_present", "_exact")}
        if (
            not field.isidentifier()
            or keyword.iskeyword(field)
            or field in _RESERVED_FIELDS
            or field.endswith("_present")
            or field in derived
        ):
            raise ValueError(f"{name}: member {field!r} has a reserved or colliding field name")
    # Fixpoint: a member whose inner variable dimensions are known supplies its outermost dimension name.
    known: set[str] = set()
    changed = True
    while changed:
        changed = False
        for layout in layouts:
            if layout.dimensions and layout.dimensions[0][0] not in known and _inner_variable(layout) <= known:
                known.add(layout.dimensions[0][0])
                changed = True
    for layout in layouts:
        missing = _inner_variable(layout) - (known if layout.path else set())
        if missing:
            raise ValueError(
                f"{name}: member {layout.field!r} has variable inner dimension(s) {sorted(missing)} "
                "that no sibling member supplies as its outermost dimension"
            )
    return layouts


def _inner_variable(layout: MemberLayout) -> set[str]:
    return {dim for dim, size in layout.dimensions[1:] if size is None}


def _flatten(layout: MemberLayout, value: Any) -> tuple[Any, tuple[int | None, ...]]:
    """Return the flat stored form of one member *value* and its shape (``None`` below an empty list).

    :param layout: The member layout.
    :param value: The member value; scalars and ``None`` pass through.
    :return: The flat value and the length of every list level.
    :raises ValueError: If a list level is not a list or ragged lists cannot be stored rectangularly.
    """
    if value is None or not layout.dimensions:
        return value, ()
    items: list[Any] = [value]
    shape: list[int | None] = []
    for depth in range(len(layout.dimensions)):
        if not all(isinstance(item, list | tuple) for item in items):
            raise ValueError(f"member {layout.field!r}: list level {depth} holds a non-list value")
        lengths = {len(item) for item in items}
        if len(lengths) > 1:
            raise ValueError(f"member {layout.field!r}: ragged lists at level {depth} (lengths {sorted(lengths)})")
        shape.append(lengths.pop() if lengths else None)
        items = [element for item in items for element in item]
    return tuple(items), tuple(shape)


def _resolve_sizes(layouts: tuple[MemberLayout, ...], flats: Mapping[str, Any]) -> dict[str, tuple[int, ...]]:
    """Resolve every present list member's per-level sizes from the definition and its siblings' flat values.

    :param layouts: The definition's member layouts.
    :param flats: The flat value of every field.
    :return: The sizes of every list field whose flat value is not ``None``.
    :raises ValueError: If sizes are inconsistent, a flat length does not divide, or a dimension is unknown.
    """
    lengths: dict[str, int] = {}
    pending = [layout for layout in layouts if layout.dimensions and flats.get(layout.field) is not None]
    resolved: dict[str, tuple[int, ...]] = {}

    def step(guess_empty: bool) -> bool:
        progress = False
        for layout in pending:
            if layout.field in resolved:
                continue
            sizes = [size if size is not None else lengths.get(dim) for dim, size in layout.dimensions]
            inner = sizes[1:]
            if None in inner:
                continue
            total, product = len(flats[layout.field]), math.prod(s for s in inner if s is not None)
            outer = sizes[0]
            if outer is None:
                if product:
                    if total % product:
                        raise ValueError(f"member {layout.field!r}: {total} items do not divide into rows of {product}")
                    outer = total // product
                elif not guess_empty:
                    continue  # Only a sibling knows how many empty rows there are; defer to it.
                elif total:
                    raise ValueError(f"member {layout.field!r}: {total} items cannot fill empty inner lists")
                else:
                    # ponytail: no sibling supplies the row count of empty rows, so assume none;
                    # _flatten_value rejects any value this would shorten.
                    outer = 0
            elif outer * product != total:
                raise ValueError(f"member {layout.field!r}: {total} items do not fill shape {[outer, *inner]}")
            dim = layout.dimensions[0][0]
            if lengths.setdefault(dim, outer) != outer:
                raise ValueError(
                    f"member {layout.field!r}: length {outer} along dimension {dim!r} contradicts {lengths[dim]}"
                )
            resolved[layout.field] = (outer, *(s for s in inner if s is not None))
            progress = True
        return progress

    while step(False) or step(True):
        pass
    for layout in pending:
        if layout.field not in resolved:
            unknown = sorted({dim for dim, size in layout.dimensions[1:] if size is None and dim not in lengths})
            raise ValueError(f"member {layout.field!r}: cannot reassemble, dimension(s) {unknown} unknown")
    return resolved


def _nest(flat: tuple[Any, ...], sizes: tuple[int, ...]) -> list[Any]:
    items: list[Any] = list(flat)
    for depth in range(len(sizes) - 1, 0, -1):
        width, rows = sizes[depth], math.prod(sizes[:depth])
        items = [items[row * width : (row + 1) * width] for row in range(rows)]
    return items


def _flatten_value(layouts: tuple[MemberLayout, ...], value: Any) -> dict[str, Any]:
    """Flatten a whole JSON-like *value* into ``{field: flat}``.

    :param layouts: The definition's member layouts (from :func:`member_layout`).
    :param value: The value; a dictionary for a dictionary definition.
    :return: The flat value of every field; absent non-required members map to ``None``.
    :raises ValueError: If *value* is ``None``, is not a dictionary where one is needed, has unknown or
        missing required members, or cannot be flattened so that it reassembles to the same shape.
    """
    if value is None:
        raise ValueError("a typed record value must not be None")
    if len(layouts) == 1 and not layouts[0].path:
        members = {layouts[0].field: value}
    else:
        if not isinstance(value, Mapping):
            raise ValueError(f"a dictionary value is required, got {type(value).__name__}")
        known = {layout.field for layout in layouts}
        unknown = sorted(str(key) for key in value if key not in known)
        missing = sorted(layout.field for layout in layouts if layout.required and layout.field not in value)
        if unknown or missing:
            raise ValueError(f"value has unknown member(s) {unknown} or lacks required member(s) {missing}")
        members = {layout.field: value.get(layout.field) for layout in layouts}
    flats: dict[str, Any] = {}
    shapes: dict[str, tuple[int | None, ...]] = {}
    for layout in layouts:
        flats[layout.field], shapes[layout.field] = _flatten(layout, members[layout.field])
    for field, sizes in _resolve_sizes(layouts, flats).items():
        if any(actual is not None and actual != size for actual, size in zip(shapes[field], sizes, strict=True)):
            raise ValueError(f"member {field!r}: shape {list(shapes[field])} would reassemble as {list(sizes)}")
    return flats


def _reassemble_value(layouts: tuple[MemberLayout, ...], flats: Mapping[str, Any]) -> Any:
    """Reassemble the JSON value from flat field values.

    Required members are always present (``None`` stays ``None``); non-required members are present only
    when not ``None``.

    :param layouts: The definition's member layouts (from :func:`member_layout`).
    :param flats: The flat value of every field.
    :return: The reassembled value: nested lists for list members, a dictionary for a dictionary definition.
    :raises ValueError: If a flat list cannot be reassembled into the definition's dimensions.
    """
    sizes = _resolve_sizes(layouts, flats)
    values = {
        layout.field: _nest(flats[layout.field], sizes[layout.field])
        if layout.field in sizes
        else flats.get(layout.field)
        for layout in layouts
    }
    if len(layouts) == 1 and not layouts[0].path:
        return values[layouts[0].field]
    return {
        layout.path[0]: values[layout.field]
        for layout in layouts
        if layout.required or values[layout.field] is not None
    }


class _LazyMapping[V](Mapping[str, V]):
    """A one-key read-only mapping whose value is computed on first lookup; iteration loads nothing."""

    def __init__(self, key: str, compute: Callable[[], V]) -> None:
        self._key = key
        self._compute = compute
        self._cache: list[V] = []

    def __getitem__(self, key: str) -> V:
        if key != self._key:
            raise KeyError(key)
        if not self._cache:
            self._cache.append(self._compute())
        return self._cache[0]

    def __iter__(self) -> Iterator[str]:
        return iter((self._key,))

    def __len__(self) -> int:
        return 1


@dataclass(frozen=True)
class TypedRecordSpec:
    """The property definition a typed record class stores, resolved lazily on first use.

    :param definition_id: The IRI of the stored property definition.
    :param served_name: The served (prefixed) property name, e.g. ``"_httk_temperature"``.
    :param derivation: The derivation-term IRI for a record of a statistic of the base property
        ``definition_id``, else ``None``.
    :param derivation_label: The human-readable derivation name (e.g. ``"root-mean-square error"``); required
        exactly when ``derivation`` is given.
    :raises ValueError: If a name is empty or unstripped, or ``derivation_label`` is given without
        ``derivation`` or missing with it.
    """

    definition_id: str
    served_name: str
    derivation: str | None = None
    derivation_label: str | None = None

    def __post_init__(self) -> None:
        _validate_string(self.definition_id, "definition_id")
        _validate_string(self.served_name, "served_name")
        for name in ("derivation", "derivation_label"):
            if getattr(self, name) is not None:
                _validate_string(getattr(self, name), name)
        if (self.derivation_label is None) != (self.derivation is None):
            raise ValueError("Fields 'derivation' and 'derivation_label' must be given together.")

    @cached_property
    def definition(self) -> PropertyDefinition:
        """Return the (base) property definition ``definition_id``."""
        return load_property_definition(self.definition_id)

    @cached_property
    def _stored_definition(self) -> PropertyDefinition:
        """Return the unprefixed definition the record stores: :attr:`definition`, or the derived one.

        A derived definition copies the base document's type, shape and units, and gets an ad-hoc httk
        ``$id`` (unpublished), the name ``<base name>_<derivation name>``, a composed title, and a
        description naming the derivation term and the base definition.

        :return: The definition.
        """
        if self.derivation is None or self.derivation_label is None:
            return self.definition
        base = self.definition
        name = f"{base.name}_{self.derivation.rstrip('/').rsplit('/', 1)[-1]}"
        document = base.as_optimade()
        for key in ("x-optimade-implementation", "sortable"):
            document.pop(key, None)
        title = document.get("title") or base.name.replace("_", " ")
        label = self.derivation_label
        stamp = {key: value for key, value in document.get("x-optimade-definition", {}).items() if key != "label"}
        document.update(
            {
                "$id": f"{_HTTK_DEFS_BASE}/_httk_{name}",
                "title": f"{label[0].upper()}{label[1:]} of {_lower_first(title)}",
                "description": (
                    f"The {label} of the property {self.definition_id}, as identified by the derivation term "
                    f"{self.derivation}.\n\n{base.description}"
                ),
                "x-optimade-definition": {**stamp, "name": name},
            }
        )
        return PropertyDefinition.from_optimade(name, document)

    @cached_property
    def served_definition(self) -> PropertyDefinition:
        """Return the served property definition; its name must be ``served_name``.

        :return: The served form of the base definition, or of the synthesized derived definition.
        :raises ValueError: If the served definition is named otherwise.
        """
        served = self._stored_definition.served_form()
        if served.name != self.served_name:
            raise ValueError(f"{self.definition_id} is served as {served.name!r}, not {self.served_name!r}")
        return served

    @cached_property
    def layout(self) -> tuple[MemberLayout, ...]:
        """Return the member layout of the stored (base or derived) definition."""
        return member_layout(self._stored_definition)

    def definitions(self) -> Mapping[str, PropertyDefinition]:
        """Return ``{served_name: served definition}``, loaded on first lookup.

        :return: A lazy read-only mapping; iterating it or taking its length loads nothing.
        """
        return _LazyMapping(self.served_name, lambda: self.served_definition)

    def projections(self) -> Mapping[str, StoredPropertyProjection]:
        """Return ``{served_name: projection}`` serving and querying the value, built on first lookup.

        Scalars are queried on their column: comparisons, string matching and ``IS KNOWN``/``IS UNKNOWN``;
        float equality is exact binary64 equality. A list member (or list value) supports ``HAS``,
        ``HAS ALL``, ``HAS ANY`` and ``HAS ONLY`` when one-dimensional (exact binary64 equality on floats;
        ``HAS ONLY`` ignores null elements) and ``LENGTH``, the outer length, when every inner size is fixed.
        A dictionary value serves its members as nested names (``name.member``) and is always known.

        :return: A lazy read-only mapping; iterating it or taking its length loads nothing.
        """
        return _LazyMapping(self.served_name, lambda: _projection(self.layout))


_STANDARD_FIELDS = ("product_of", "id", "immutable_id", "last_modified")
_COMPARISONS = frozenset({"=", "!=", "<", "<=", ">", ">=", "CONTAINS", "STARTS", "ENDS"})
_VERIFIED_CLASSES: set[type] = set()


def _check_class(cls: type, layout: tuple[MemberLayout, ...]) -> None:
    """Verify once per class that *cls* is a frozen dataclass whose fields match *layout*.

    :param cls: The typed record class.
    :param layout: Its spec's layout.
    :raises TypeError: If the class is not frozen or its fields differ from the layout.
    """
    if cls in _VERIFIED_CLASSES:
        return
    expected = [item.field for item in layout if item.required] + [item.field for item in layout if not item.required]
    actual = [item.name for item in fields(cast(Any, cls))]
    if not cast(Any, cls).__dataclass_params__.frozen or actual != [*expected, *_STANDARD_FIELDS]:
        raise TypeError(
            f"{cls.__name__} must be a frozen dataclass with fields {[*expected, *_STANDARD_FIELDS]}, has {actual}"
        )
    _VERIFIED_CLASSES.add(cls)


def _coerce_leaf(field: str, leaf: str, value: Any) -> Any:
    if leaf == "float" and isinstance(value, bool):
        raise ValueError(f"Field {field!r} must hold numbers, not booleans.")
    return float(value) if leaf == "float" and isinstance(value, int) else value


class TypedRecord:
    """Mixin base of generated typed result records: one frozen dataclass per property definition.

    A subclass sets ``__httk_typed_record__`` to its :class:`TypedRecordSpec` and declares the layout's
    value fields (required members, then non-required members defaulting to ``None``) followed by the
    standard ``product_of``, ``id``, ``immutable_id`` and ``last_modified`` fields. Construction coerces
    integers to floats for float members and lists to tuples, validates the provenance edges and the
    timestamp, and checks the reassembled :attr:`value` against the served definition. The value itself is
    never ``None``, even for a nullable definition; dictionary members may be ``None`` when nullable or
    not required.
    """

    __httk_typed_record__: ClassVar[TypedRecordSpec]

    @property
    def type(self) -> str:
        """Return the internal (unprefixed) entry type name."""
        return "records"

    @property
    def definition_id(self) -> str:
        """Return the IRI of the property definition whose value this record holds, as on ``DataRecord``.

        For a derived (statistics) kind this is the base definition, qualified by :attr:`derivation`.
        """
        return self.__httk_typed_record__.definition_id

    @property
    def derivation(self) -> str | None:
        """Return the derivation-term IRI qualifying :attr:`definition_id`, as on ``DerivedDataRecord``; ``None`` for a plain kind."""
        return self.__httk_typed_record__.derivation

    @property
    def value(self) -> Any:
        """Return the JSON value reassembled from the record's fields."""
        layout = self.__httk_typed_record__.layout
        return _reassemble_value(layout, {item.field: getattr(self, item.field) for item in layout})

    def __post_init__(self) -> None:
        cls = self.__class__
        spec = self.__httk_typed_record__
        _check_class(cls, spec.layout)
        for item in spec.layout:
            value = getattr(self, item.field)
            if value is None:
                if not item.path:
                    raise ValueError(f"Field {item.field!r} must not be None; a typed record holds a value.")
                continue
            if item.dimensions:
                if not isinstance(value, list | tuple):
                    raise ValueError(f"Field {item.field!r} must be a flat list or tuple.")
                value = tuple(_coerce_leaf(item.field, item.leaf, element) for element in value)
            else:
                value = _coerce_leaf(item.field, item.leaf, value)
            object.__setattr__(self, item.field, value)
        edges = _edges(getattr(self, "product_of"))  # noqa: B009
        if len({edge.label for edge in edges}) != len(edges):
            raise ValueError(f"Duplicate label on {cls.__name__} product_of.")
        object.__setattr__(self, "product_of", edges)
        _validate_timestamp(getattr(self, "last_modified"), "last_modified")  # noqa: B009
        spec.served_definition.check(self.value)

    @classmethod
    def from_value(
        cls,
        value: Any,
        *,
        product_of: Iterable[RunEdge | Mapping[str, Any]] = (),
        id: str | None = None,
        immutable_id: str | None = None,
        last_modified: datetime.datetime | None = None,
    ) -> Self:
        """Build a record from a JSON-like value of the definition.

        :param value: The property value (a dictionary for a dictionary definition); never ``None``.
        :param product_of: The entries this value is a product of, as labeled edges.
        :param id: The human-readable entry id shared by all revisions; minted by the store when None.
        :param immutable_id: The per-revision immutable id; minted by the store when None.
        :param last_modified: The optional timezone-aware metadata timestamp.
        :return: The typed record.
        :raises ValueError: If the value is ``None``, cannot be flattened, or fails the definition check.
        """
        flats = _flatten_value(cls.__httk_typed_record__.layout, value)
        return cast(Any, cls)(
            **flats, product_of=product_of, id=id, immutable_id=immutable_id, last_modified=last_modified
        )

    @classmethod
    def from_data_record(cls, record: DataRecord) -> Self:
        """Build a typed record from the generic data record of the same property definition.

        The generic record's ``name`` is not kept, since the class fixes the property; its value, provenance
        edges, ids and timestamp are.

        :param record: A data record whose definition is this kind's property definition.
        :return: The typed record.
        :raises TypeError: If this is a derived (statistics) kind.
        :raises ValueError: If ``record`` is not a data record of this kind's definition, or its value is
            ``None`` or fails the definition.
        """
        spec = cls.__httk_typed_record__
        if spec.derivation is not None:
            raise TypeError("derived typed records are built with from_value")
        if not isinstance(record, DataRecord):
            raise ValueError(f"Expected a DataRecord of {spec.definition_id!r}, got {type(record).__name__}.")
        if record.definition_id != spec.definition_id:
            raise ValueError(f"DataRecord definition {record.definition_id!r} is not {spec.definition_id!r}.")
        return cls.from_value(
            record.value,
            product_of=record.product_of,
            id=record.id,
            immutable_id=record.immutable_id,
            last_modified=record.last_modified,
        )


def _scalar_projection(field: str) -> StoredPropertyProjection:
    def query(context: QueryContext, operator: str, literal: object) -> QueryExpression:
        value = context.field(field)
        if operator == "IS_KNOWN":
            return context.not_(context.is_null(value))
        if operator == "IS_UNKNOWN":
            return context.is_null(value)
        if operator in _COMPARISONS:
            return context.compare(value, operator, context.constant(literal))
        raise QueryLiteralError(f"{field} supports comparisons, string matching and IS KNOWN/UNKNOWN only")

    return StoredPropertyProjection(
        response=lambda record: getattr(record, field), query=query, sort=lambda context: context.field(field)
    )


def _list_projection(layout: MemberLayout, response: Callable[[object], object]) -> StoredPropertyProjection:
    field = layout.field
    inner = [size for _, size in layout.dimensions[1:]]
    # A dictionary member may be None (absent or null); a top-level value never is.
    maybe_none = bool(layout.path) and (layout.nullable or not layout.required)

    def present(context: QueryContext, flag: bool) -> QueryExpression:
        return context.equal(context.field(f"{field}_present"), context.constant(flag))

    def query(context: QueryContext, operator: str, literal: object) -> QueryExpression:
        if operator in ("IS_KNOWN", "IS_UNKNOWN"):
            if not maybe_none:
                return context.always_true() if operator == "IS_KNOWN" else context.always_false()
            return present(context, operator == "IS_KNOWN")
        if operator.startswith("LENGTH "):
            if None in inner or 0 in inner or not isinstance(literal, int) or isinstance(literal, bool):
                raise QueryLiteralError(f"{field} LENGTH needs an integer literal and fixed inner sizes")
            rows = context.count(context.scope(field))
            factor = math.prod(size for size in inner if size is not None)
            predicate = context.compare(rows, operator.removeprefix("LENGTH "), context.constant(literal * factor))
        elif operator in ("HAS_ALL", "HAS_ANY", "HAS_ONLY"):
            if inner or not isinstance(literal, list | tuple):
                raise QueryLiteralError(f"{field} supports HAS only on a one-dimensional list, with a list literal")
            if operator == "HAS_ONLY":
                scope = context.scope(field)
                others = context.and_(
                    *(context.not_(context.equal(scope.field("value"), context.constant(x))) for x in literal)
                )
                predicate = context.compare(context.count(context.filtered(scope, others)), "=", context.constant(0))
            else:
                terms = []
                for x in literal:
                    scope = context.scope(field)  # A fresh peer scope per term.
                    matching = context.filtered(scope, context.equal(scope.field("value"), context.constant(x)))
                    terms.append(context.compare(context.count(matching), ">", context.constant(0)))
                predicate = context.and_(*terms) if operator == "HAS_ALL" else context.or_(*terms)
        else:
            raise QueryLiteralError(f"{field} supports HAS, LENGTH and IS KNOWN/UNKNOWN only")
        return context.when_known(present(context, True), predicate) if maybe_none else predicate

    return StoredPropertyProjection(response=response, query=query)


def _dictionary_query(context: QueryContext, operator: str, literal: object) -> QueryExpression:
    if operator == "IS_KNOWN":
        return context.always_true()
    if operator == "IS_UNKNOWN":
        return context.always_false()
    raise QueryLiteralError("a dictionary value supports only IS KNOWN/UNKNOWN; filter on its members")


def _value(record: object) -> object:
    return cast(TypedRecord, record).value


def _projection(layout: tuple[MemberLayout, ...]) -> StoredPropertyProjection:
    """Build the projection of a typed record's served value from its layout.

    :param layout: The definition's member layout.
    :return: The top-level projection, with member projections for a dictionary definition.
    """
    if len(layout) == 1 and not layout[0].path:
        item = layout[0]
        return _list_projection(item, _value) if item.dimensions else _scalar_projection(item.field)

    def member(item: MemberLayout) -> StoredPropertyProjection:
        if not item.dimensions:
            return _scalar_projection(item.field)
        return _list_projection(item, lambda record: cast(dict[str, Any], _value(record)).get(item.path[0]))

    return StoredPropertyProjection(
        response=_value, query=_dictionary_query, members={item.path[0]: member(item) for item in layout}
    )
