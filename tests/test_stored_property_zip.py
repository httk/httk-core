import dataclasses
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import pytest

from httk.core.storage import (
    QueryContext,
    QueryExpression,
    StoredPropertyProjection,
    StoredPropertyZipQuery,
    ZipLiteral,
    stored_property_projections,
)


def _response(record: Any) -> object:
    return record.values


def _zip_query(context: QueryContext, operator: str, literal: ZipLiteral) -> QueryExpression | None:
    return None


def test_zip_literal_is_frozen_value() -> None:
    literal = ZipLiteral(paths=("a", "b"), operators=(("=", ">"),), values=(("x", 1),))
    assert literal == ZipLiteral(("a", "b"), (("=", ">"),), (("x", 1),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        literal.paths = ("c",)  # type: ignore[misc]


def test_projection_accepts_callable_zip_query() -> None:
    query: StoredPropertyZipQuery = _zip_query
    projection = StoredPropertyProjection(response=_response, zip_query=query)
    assert projection.zip_query is _zip_query
    assert StoredPropertyProjection(response=_response).zip_query is None


def test_projection_rejects_non_callable_zip_query() -> None:
    with pytest.raises(TypeError, match="zip_query must be callable or None"):
        StoredPropertyProjection(response=_response, zip_query=cast(Any, "not callable"))


@dataclass(frozen=True)
class ZipRecord:
    values: tuple[int, ...]

    __httk_stored_properties__: ClassVar[dict[str, StoredPropertyProjection]] = {
        "values": StoredPropertyProjection(response=_response, zip_query=_zip_query),
    }


def test_projection_map_with_zip_query_validates() -> None:
    projections = stored_property_projections(ZipRecord)
    assert projections["values"].zip_query is _zip_query
