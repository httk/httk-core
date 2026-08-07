"""Backend-neutral declarations for properties of durable entry backings.

An entry family may have several concrete durable representations.  Each
backing declares its own served-property map with
:class:`StoredPropertyProjection`; the declaration remains entirely in the
domain package while a storage implementation translates its query callbacks
to its native query language.  Nothing here assumes SQL, OPTIMADE, or a
particular record family.

The query protocols deliberately describe expression *construction*, rather
than expression evaluation.  A domain callback only receives a
:class:`QueryContext`; the storage backend supplies its implementation and is
therefore free to use SQL, a document query, or an in-memory evaluator.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Protocol

__all__ = [
    "STORED_PROPERTY_PROJECTIONS_ATTRIBUTE",
    "QueryContext",
    "QueryExpression",
    "QueryField",
    "QueryLiteralError",
    "QueryScope",
    "QueryValue",
    "StoredPropertyProjection",
    "StoredPropertyQuery",
    "StoredPropertyResponse",
    "StoredPropertySort",
    "stored_property_projections",
]


STORED_PROPERTY_PROJECTIONS_ATTRIBUTE: Final = "__httk_stored_properties__"
"""Exact-class attribute holding a backing's property-projection mapping."""

_MISSING = object()
_EMPTY_PROJECTIONS: Mapping[str, "StoredPropertyProjection"] = MappingProxyType({})


class QueryLiteralError(ValueError):
    """A query literal cannot represent the property value requested.

    This is intentionally distinct from a query expression which simply
    matches no records.  Protocol layers can translate it into their
    user-facing invalid-filter-value error without depending on a domain
    package's parser exception.
    """


class QueryExpression(Protocol):
    """One backend-neutral boolean predicate.

    Query callbacks compose predicates with the ordinary boolean operators;
    the backend decides how to retain SQL's three-valued null semantics (or an
    equivalent semantics in another storage engine).
    """

    def __and__(self, other: "QueryExpression") -> "QueryExpression": ...

    def __or__(self, other: "QueryExpression") -> "QueryExpression": ...

    def __invert__(self) -> "QueryExpression": ...


class QueryValue(Protocol):
    """A scalar or aggregate value participating in a query expression."""


class QueryField(QueryValue, Protocol):
    """A durable field selected from a :class:`QueryScope`."""


class QueryScope(Protocol):
    """A record or correlated child/reference scope.

    ``scope(name)`` follows a durable reference or child relationship while
    retaining correlation to this scope.  It intentionally does not say
    whether that relationship is one-to-one or a collection: ``exists`` and
    the aggregate methods on :class:`QueryContext` give both cases a single,
    portable vocabulary.  Every ``scope`` call creates a distinct peer scope,
    even for the same relationship name, so a callback can compare correlated
    child rows without an accidental self-alias.
    """

    def field(self, name: str) -> QueryField:
        """Return the durable scalar field named ``name`` in this scope.

        :param name: The durable field name.
        :return: A query value representing that field.
        """
        ...

    def scope(self, name: str) -> "QueryScope":
        """Return the correlated child or reference scope named ``name``.

        :param name: The durable relationship name.
        :return: A distinct correlated peer scope.
        """
        ...


class QueryContext(QueryScope, Protocol):
    """Factory and algebra used by domain-owned property query callbacks.

    ``field`` and ``scope`` start at the backing record.  ``scope`` can be
    called again on a child/reference scope, so callbacks can express
    correlated nested predicates without seeing storage tables or joins.
    ``exact_equal`` requests equality in the property's exact stored domain;
    it is the operation to use for fractions and other values for which a
    presentation float would be lossy.
    """

    def constant(self, value: object) -> QueryValue:
        """Return a query value for an already validated literal constant.

        :param value: The validated literal to place in the query.
        :return: A query value for the literal.
        """
        ...

    def null(self) -> QueryValue:
        """Return the explicit null query value.

        :return: A query value representing null.
        """
        ...

    def always_true(self) -> QueryExpression:
        """Return the predicate which matches every backing record.

        :return: A predicate that always matches.
        """
        ...

    def always_false(self) -> QueryExpression:
        """Return the predicate which matches no backing record.

        :return: A predicate that never matches.
        """
        ...

    def compare(self, left: QueryValue, operator: str, right: QueryValue) -> QueryExpression:
        """Compare values with a backend-supported comparison operator.

        Domain callbacks normally use :meth:`equal`, :meth:`exact_equal`, or
        explicit operator dispatch for a protocol's filter grammar.  The
        operator is deliberately a string so this contract does not own an
        external query language's token enum.

        :param left: The left query value.
        :param operator: The backend-supported comparison operator.
        :param right: The right query value.
        :return: The comparison predicate.
        """
        ...

    def equal(self, left: QueryValue, right: QueryValue) -> QueryExpression:
        """Compare values using the backing's ordinary stored semantics.

        :param left: The left query value.
        :param right: The right query value.
        :return: The equality predicate.
        """
        ...

    def exact_equal(self, left: QueryValue, right: QueryValue) -> QueryExpression:
        """Compare values in their exact canonical stored representation.

        :param left: The left query value.
        :param right: The right query value.
        :return: The exact equality predicate.
        """
        ...

    def is_null(self, value: QueryValue) -> QueryExpression:
        """Test a value for null; invert this predicate for a known-value test.

        :param value: The query value to test.
        :return: The null-test predicate.
        """
        ...

    def exists(self, scope: QueryScope, predicate: QueryExpression) -> QueryExpression:
        """Test whether a correlated scope contains a row satisfying ``predicate``.

        :param scope: The correlated scope to inspect.
        :param predicate: The predicate required of a matching row.
        :return: The existence predicate.
        """
        ...

    def filtered(self, scope: QueryScope, predicate: QueryExpression) -> QueryScope:
        """Return the correlated subset of ``scope`` satisfying ``predicate``.

        The returned scope is usable by aggregate operations.  In particular,
        it lets a declaration compare a required multiplicity with the exact
        number of matching child values rather than reusing one ``exists``
        witness for repeated values.

        :param scope: The correlated scope to filter.
        :param predicate: The predicate required of retained rows.
        :return: A correlated scope containing only matching rows.
        """
        ...

    def count(self, scope: QueryScope) -> QueryValue:
        """Return the number of rows in a correlated child/reference scope.

        :param scope: The correlated scope to count.
        :return: A query value containing the row count.
        """
        ...

    def distinct_count(self, scope: QueryScope, value: QueryValue) -> QueryValue:
        """Return the count of distinct ``value`` values in ``scope``.

        :param scope: The correlated scope to count.
        :param value: The value whose distinct occurrences are counted.
        :return: A query value containing the distinct count.
        """
        ...

    def scaled_exact_equal(
        self,
        left: QueryValue,
        left_factor: QueryValue,
        right: QueryValue,
        right_factor: QueryValue,
    ) -> QueryExpression:
        """Compare two exact values after cross multiplication.

        This is the portable, exact form of a proportional comparison.  It
        avoids requiring a backend to divide fractions or approximate a ratio
        through a presentation float: it asserts ``left * left_factor ==
        right * right_factor`` in the backing's canonical exact domain.

        :param left: The first exact value.
        :param left_factor: The factor applied to the first value.
        :param right: The second exact value.
        :param right_factor: The factor applied to the second value.
        :return: The cross-multiplied equality predicate.
        """
        ...

    def and_(self, *predicates: QueryExpression) -> QueryExpression:
        r"""Conjoin predicates; an empty conjunction is :meth:`always_true`.

        :param \*predicates: The predicates to conjoin.
        :return: The conjunction predicate.
        """
        ...

    def or_(self, *predicates: QueryExpression) -> QueryExpression:
        r"""Disjoin predicates; an empty disjunction is :meth:`always_false`.

        :param \*predicates: The predicates to disjoin.
        :return: The disjunction predicate.
        """
        ...

    def not_(self, predicate: QueryExpression) -> QueryExpression:
        """Negate a predicate without relying on a backend's Python truthiness.

        :param predicate: The predicate to negate.
        :return: The negated predicate.
        """
        ...

    def when_known(self, known: QueryExpression, predicate: QueryExpression) -> QueryExpression:
        """Evaluate ``predicate`` only when ``known`` is true, else return unknown.

        This is the backend-neutral three-valued-logic form of ``CASE WHEN
        known THEN predicate ELSE NULL END``.  It keeps incomplete nullable
        domain data unknown under both a predicate and its negation instead
        of silently treating the missing representation as a non-match.

        :param known: The predicate establishing that the value is available.
        :param predicate: The predicate evaluated only when ``known`` matches.
        :return: The conditional three-valued predicate.
        """
        ...


type StoredPropertyResponse = Callable[[object], object]
"""Extract one served property value from one concrete backing record."""

type StoredPropertyQuery = Callable[[QueryContext, str, object], QueryExpression]
"""Build one predicate from a context, protocol operator, and parsed literal."""

type StoredPropertySort = Callable[[QueryContext], QueryValue]
"""Select one sortable backing value from a query context."""


@dataclass(frozen=True, slots=True)
class StoredPropertyProjection:
    """One domain-owned projection of a served property for one backing.

    ``response`` is called with a concrete backing record and returns its
    protocol-boundary value.  ``query`` receives a backend-neutral context,
    the protocol comparison operator, and its parsed literal; it returns a
    predicate or raises :class:`QueryLiteralError` when the literal has no
    valid representation for this property.  ``None`` means that a property
    is response-only for this backing.  ``sort`` identifies a direct sortable
    value and is intentionally separate from filtering because not every
    predicate has a meaningful total ordering.

    :param response: The operation that extracts the served value from a backing record.
    :param query: The optional operation that builds filtering predicates.
    :param sort: The optional operation that selects a value for ordering.
    :raises TypeError: If a supplied projection operation cannot be invoked.
    """

    response: StoredPropertyResponse
    query: StoredPropertyQuery | None = None
    sort: StoredPropertySort | None = None

    def __post_init__(self) -> None:
        if not callable(self.response):
            raise TypeError("StoredPropertyProjection.response must be callable")
        if self.query is not None and not callable(self.query):
            raise TypeError("StoredPropertyProjection.query must be callable or None")
        if self.sort is not None and not callable(self.sort):
            raise TypeError("StoredPropertyProjection.sort must be callable or None")


def stored_property_projections(cls: type[Any]) -> Mapping[str, StoredPropertyProjection]:
    """Return a validated property's projection map declared *on* ``cls``.

    The lookup deliberately uses :func:`vars` rather than :func:`getattr`.
    A representation-specific property mapping must be opted into by the
    exact backing class; subclasses never inherit a parent's mapping by
    accident.  A class without the declaration serves no stored properties.

    :param cls: The exact frozen dataclass backing class to inspect.
    :return: Its validated projection map, or an empty map when undeclared.
    :raises TypeError: If ``cls`` is not a directly declared frozen dataclass or its map is invalid.
    :raises ValueError: If a projection name is invalid.
    """

    if not isinstance(cls, type):
        raise TypeError(f"stored-property projection target must be a class, got {type(cls).__name__}")
    namespace = vars(cls)
    params = namespace.get("__dataclass_params__")
    declared_fields = namespace.get("__dataclass_fields__")
    if params is None or declared_fields is None:
        raise TypeError(
            f"stored-property projection target {cls.__name__} must be declared directly as a frozen dataclass"
        )
    if not params.frozen:
        raise TypeError(f"stored-property projection target {cls.__name__} must be a frozen dataclass")

    value = namespace.get(STORED_PROPERTY_PROJECTIONS_ATTRIBUTE, _MISSING)
    if value is _MISSING:
        return _EMPTY_PROJECTIONS
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{cls.__name__}.{STORED_PROPERTY_PROJECTIONS_ATTRIBUTE} must be a mapping of "
            "property names to StoredPropertyProjection values"
        )

    projections = dict(value)
    for name, projection in projections.items():
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError("stored-property projection names must be non-empty stripped strings")
        if not isinstance(projection, StoredPropertyProjection):
            raise TypeError(
                f"{cls.__name__}.{STORED_PROPERTY_PROJECTIONS_ATTRIBUTE}[{name!r}] must be a StoredPropertyProjection"
            )
    return MappingProxyType(projections)
