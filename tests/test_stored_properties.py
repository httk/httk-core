from dataclasses import dataclass
from typing import Any, cast

import pytest

from httk.core.storage import (
    QueryContext,
    QueryExpression,
    QueryLiteralError,
    QueryValue,
    StoredPropertyProjection,
    stored_property_projections,
)


def _formula_response(record: Any) -> object:
    return record.formula


def _formula_query(context: QueryContext, operator: str, literal: object) -> QueryExpression:
    if operator != "=":
        raise QueryLiteralError("formula supports exact equality only")
    if not isinstance(literal, str) or not literal:
        raise QueryLiteralError("formula must be a non-empty string")
    return context.exact_equal(context.field("formula"), context.constant(literal))


def _formula_sort(context: QueryContext) -> QueryValue:
    return context.field("formula")


@dataclass(frozen=True)
class EntryRecord:
    formula: str

    __httk_stored_properties__ = {
        "chemical_formula_reduced": StoredPropertyProjection(
            response=_formula_response,
            query=_formula_query,
            sort=_formula_sort,
        )
    }


class _ProbeContext:
    def field(self, name: str) -> QueryValue:
        return cast(QueryValue, ("field", name))

    def constant(self, value: object) -> QueryValue:
        return cast(QueryValue, ("constant", value))

    def exact_equal(self, left: QueryValue, right: QueryValue) -> QueryExpression:
        return cast(QueryExpression, ("exact_equal", left, right))

    def when_known(self, known: QueryExpression, predicate: QueryExpression) -> QueryExpression:
        return cast(QueryExpression, ("when_known", known, predicate))


def test_stored_property_projections_are_immutable_and_invoke_domain_callbacks() -> None:
    projections = stored_property_projections(EntryRecord)
    projection = projections["chemical_formula_reduced"]
    assert projection.response(EntryRecord("Fe2O3")) == "Fe2O3"
    assert projection.query is not None
    assert projection.query(cast(QueryContext, _ProbeContext()), "=", "Fe2O3") == (
        "exact_equal",
        ("field", "formula"),
        ("constant", "Fe2O3"),
    )
    assert projection.sort is not None
    assert projection.sort(cast(QueryContext, _ProbeContext())) == ("field", "formula")
    with pytest.raises(TypeError):
        projections["elements"] = projection


def test_property_projections_use_exact_class_declarations() -> None:
    @dataclass(frozen=True)
    class DerivedRecord(EntryRecord):
        label: str

    assert stored_property_projections(DerivedRecord) == {}

    class MutableSubclass(EntryRecord):
        __httk_stored_properties__ = EntryRecord.__httk_stored_properties__
        __setattr__ = object.__setattr__

    mutable = MutableSubclass("Fe")
    mutable.formula = "O"
    assert mutable.formula == "O"
    with pytest.raises(TypeError, match="declared directly as a frozen dataclass"):
        stored_property_projections(MutableSubclass)


def test_stored_property_projection_rejects_invalid_contracts() -> None:
    with pytest.raises(TypeError, match="response"):
        StoredPropertyProjection(response=cast(Any, "not callable"))
    with pytest.raises(TypeError, match="query"):
        StoredPropertyProjection(response=_formula_response, query=cast(Any, "not callable"))
    with pytest.raises(TypeError, match="sort"):
        StoredPropertyProjection(response=_formula_response, sort=cast(Any, "not callable"))

    @dataclass(frozen=True)
    class BrokenValue:
        value: str

        __httk_stored_properties__ = {"id": cast(Any, _formula_response)}

    with pytest.raises(TypeError, match="StoredPropertyProjection"):
        stored_property_projections(BrokenValue)

    @dataclass(frozen=True)
    class BrokenName:
        value: str

        __httk_stored_properties__ = {" ": StoredPropertyProjection(response=_formula_response)}

    with pytest.raises(ValueError, match="non-empty stripped"):
        stored_property_projections(BrokenName)

    @dataclass
    class MutableRecord:
        value: str

        __httk_stored_properties__ = {"value": StoredPropertyProjection(response=_formula_response)}

    with pytest.raises(TypeError, match="frozen dataclass"):
        stored_property_projections(MutableRecord)


def test_query_literal_errors_remain_distinct_from_no_match() -> None:
    projection = stored_property_projections(EntryRecord)["chemical_formula_reduced"]
    assert projection.query is not None
    with pytest.raises(QueryLiteralError, match="non-empty"):
        projection.query(cast(QueryContext, _ProbeContext()), "=", "")


def test_query_context_can_preserve_unknown_for_incomplete_values() -> None:
    context = cast(QueryContext, _ProbeContext())
    known = cast(QueryExpression, ("known",))
    predicate = cast(QueryExpression, ("predicate",))
    assert context.when_known(known, predicate) == ("when_known", known, predicate)
