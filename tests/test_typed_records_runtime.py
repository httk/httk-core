"""Tests for the typed-record runtime: construction, values, lazy declarations and query projections."""

import datetime
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, ClassVar, cast

import pytest

from httk.core import (
    DataRecord,
    DerivedDataRecord,
    IdentitySkip,
    Indexed,
    PropertyDefinition,
    RunEdge,
    StrongLink,
    TypedRecord,
    TypedRecordSpec,
    Unique,
    load_property_definition,
    typed_records,
)
from httk.core.definition_ids import STRESS_TENSOR, TEMPERATURE
from httk.core.storage import QueryLiteralError, StoredPropertyProjection
from httk.core.typed_records import member_layout

SAMPLE_ID = "https://schemas.httk.org/defs/v0.1/properties/test/sample"
RMSE = "https://schemas.httk.org/defs/v0.1/derivations/rmse"
STANDARD_ERROR = "https://schemas.httk.org/defs/v0.1/derivations/standard_error"


def _leaf(json_type: str, kind: str, nullable: bool = False) -> dict[str, Any]:
    return {"x-optimade-type": kind, "type": [json_type, "null"] if nullable else [json_type]}


def _list(items: dict[str, Any], name: str, size: int | None) -> dict[str, Any]:
    dims = {"names": [name], "sizes": [size]}
    return {"x-optimade-type": "list", "type": ["array"], "x-optimade-dimensions": dims, "items": items}


SAMPLE = PropertyDefinition.from_optimade(
    "sample",
    {
        "$id": SAMPLE_ID,
        "description": "A test dictionary.",
        "x-optimade-type": "dictionary",
        "type": ["object", "null"],
        "required": ["label", "count", "offset", "matrix", "values"],
        "properties": {
            "label": {**_leaf("string", "string"), "enum": ["a", "b"]},
            "weight": _leaf("number", "float"),
            "count": _leaf("integer", "integer"),
            "offset": _leaf("number", "float", nullable=True),
            "matrix": _list(_list(_leaf("number", "float"), "cols", 3), "rows", 2),
            "tags": _list(_leaf("string", "string"), "tags", None),
            "values": _list(_leaf("number", "float", nullable=True), "points", None),
        },
    },
)


NULLABLE_ID = "https://schemas.httk.org/defs/v0.1/properties/test/nullable_points"
NULLABLE = PropertyDefinition.from_optimade(
    "nullable_points",
    {
        "$id": NULLABLE_ID,
        "description": "A dictionary with a required but nullable list member.",
        "x-optimade-type": "dictionary",
        "type": ["object", "null"],
        "required": ["points"],
        "properties": {"points": {**_list(_leaf("number", "float"), "points", None), "type": ["array", "null"]}},
    },
)
NVE_ID = "https://schemas.httk.org/defs/v0.1/properties/test/nve_energy_drift"
NVE = PropertyDefinition.from_optimade(
    "nve_energy_drift",
    {"$id": NVE_ID, "title": "NVE energy drift", "description": "A drift.", **_leaf("number", "float", True)},
)
_TEST_DEFINITIONS = {SAMPLE_ID: SAMPLE, NULLABLE_ID: NULLABLE, NVE_ID: NVE}


@pytest.fixture(autouse=True)
def _sample_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    def load(definition_id: str) -> PropertyDefinition:
        return _TEST_DEFINITIONS.get(definition_id) or load_property_definition(definition_id)

    monkeypatch.setattr(typed_records, "load_property_definition", load)


type Edges = Annotated[tuple[RunEdge, ...], StrongLink("product_of", reverse="has_product", role="subject")]


@dataclass(frozen=True)
class Temperature(TypedRecord):
    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(TEMPERATURE, "_httk_temperature")

    temperature: float
    product_of: Edges = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)


@dataclass(frozen=True)
class Stress(TypedRecord):
    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(STRESS_TENSOR, "_httk_stress_tensor")

    stress_tensor: tuple[float, ...]
    product_of: Edges = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)


@dataclass(frozen=True)
class Sample(TypedRecord):
    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(SAMPLE_ID, "_httk_sample")

    label: str
    count: int
    offset: float | None
    matrix: tuple[float, ...]
    values: tuple[float | None, ...]
    weight: float | None = None
    tags: tuple[str, ...] | None = None
    product_of: Edges = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)


SAMPLE_VALUE = {
    "label": "a",
    "count": 2,
    "offset": None,
    "matrix": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
    "values": [0.5, None],
}


# --- Construction and values ---------------------------------------------------------------------------


def test_scalar_record_coerces_and_checks() -> None:
    record = Temperature(300)
    assert record.temperature == 300.0 and isinstance(record.temperature, float)
    assert record.value == 300.0 and record.type == "records"
    assert record.definition_id == TEMPERATURE and record.derivation is None
    assert Temperature.from_value(250.5) == Temperature(250.5)
    with pytest.raises(ValueError, match="booleans"):
        Temperature(cast(Any, True))
    with pytest.raises(ValueError, match="must not be None"):
        Temperature(cast(Any, None))
    with pytest.raises(ValueError, match="must not be None"):
        Temperature.from_value(None)


def test_list_record_coerces_and_checks() -> None:
    record = Stress(cast(Any, [1, 2, 3, 0, 0, 0.5]))
    assert record.stress_tensor == (1.0, 2.0, 3.0, 0.0, 0.0, 0.5)
    assert all(isinstance(component, float) for component in record.stress_tensor)
    assert record.value == [1.0, 2.0, 3.0, 0.0, 0.0, 0.5]
    with pytest.raises(ValueError, match=r"do not fill shape \[6\]"):
        Stress((1.0,) * 5)
    with pytest.raises(ValueError, match="booleans"):
        Stress(cast(Any, (True,) * 6))
    with pytest.raises(ValueError, match="flat list or tuple"):
        Stress(cast(Any, "abcdef"))


def test_dictionary_record_round_trip_and_omission() -> None:
    record = Sample.from_value(SAMPLE_VALUE)
    assert record.matrix == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0) and record.values == (0.5, None)
    assert record.weight is None and record.tags is None
    assert record.value == SAMPLE_VALUE  # Required None stays; absent optional members are omitted.
    full = {**SAMPLE_VALUE, "weight": 3, "tags": ["x", "y"]}
    record = Sample.from_value(full)
    assert record.weight == 3.0 and isinstance(record.weight, float) and record.tags == ("x", "y")
    assert record.value == {**full, "weight": 3.0}
    assert Sample(**cast(Any, typed_records._flatten_value(Sample.__httk_typed_record__.layout, full))) == record


def test_dictionary_record_check_failures() -> None:
    with pytest.raises(ValueError, match="expected one of"):
        Sample.from_value({**SAMPLE_VALUE, "label": "c"})
    with pytest.raises(ValueError, match="do not fill"):
        Sample("a", 1, None, (1.0,) * 5, ())
    with pytest.raises(ValueError, match="not a valid integer"):
        Sample.from_value({**SAMPLE_VALUE, "count": 2.0})


def test_product_of_and_timestamp_validation() -> None:
    edge = RunEdge("input", "runs", "r1")
    record = Temperature(1.0, product_of=cast(Any, [edge]))
    assert record.product_of == (edge,)
    with pytest.raises(ValueError, match="Duplicate label"):
        Temperature(1.0, product_of=(edge, RunEdge("input", "runs", "r2")))
    with pytest.raises(ValueError, match="timezone-aware"):
        Temperature.from_value(1.0, last_modified=datetime.datetime(2026, 1, 1))  # noqa: DTZ001


def test_drift_guard_rejects_misordered_fields() -> None:
    @dataclass(frozen=True)
    class Misordered(TypedRecord):
        __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(SAMPLE_ID, "_httk_sample")

        label: str
        weight: float | None
        count: int
        offset: float | None
        matrix: tuple[float, ...]
        values: tuple[float | None, ...]
        tags: tuple[str, ...] | None = None
        product_of: Edges = ()
        id: str | None = None
        immutable_id: str | None = None
        last_modified: datetime.datetime | None = None

    with pytest.raises(TypeError, match="Misordered must be a frozen dataclass with fields"):
        Misordered("a", None, 1, None, (0.0,) * 6, ())


def test_spec_validation_and_served_name() -> None:
    with pytest.raises(ValueError, match="served_name"):
        TypedRecordSpec(TEMPERATURE, "")
    for derivation, label in ((None, "mean"), (RMSE, None)):
        with pytest.raises(ValueError, match="must be given together"):
            TypedRecordSpec(TEMPERATURE, "_httk_temperature", derivation, label)
    with pytest.raises(ValueError, match="not 'temperature'"):
        _ = TypedRecordSpec(TEMPERATURE, "temperature").served_definition
    with pytest.raises(ValueError, match="not '_httk_temperature_mean'"):
        _ = TypedRecordSpec(TEMPERATURE, "_httk_temperature_mean", STANDARD_ERROR, "standard error").served_definition


# --- Derived (statistics) kinds --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_id", "derivation", "label", "served_name", "title"),
    [
        (
            STRESS_TENSOR,
            RMSE,
            "root-mean-square error",
            "_httk_stress_tensor_rmse",
            "Root-mean-square error of stress tensor",
        ),
        (
            TEMPERATURE,
            STANDARD_ERROR,
            "standard error",
            "_httk_temperature_standard_error",
            "Standard error of temperature",
        ),
    ],
)
def test_derived_served_definition(base_id: str, derivation: str, label: str, served_name: str, title: str) -> None:
    spec = TypedRecordSpec(base_id, served_name, derivation, label)
    base, served = load_property_definition(base_id).as_optimade(), spec.served_definition.as_optimade()
    assert spec.served_definition.name == served_name
    unprefixed = served_name.removeprefix("_httk_")
    assert served["$id"] == f"https://schemas.httk.org/ad-hoc/defs/properties/_httk_{unprefixed}"
    assert served["title"] == title
    assert served["x-optimade-definition"]["name"] == unprefixed and "label" not in served["x-optimade-definition"]
    assert served["description"].startswith(
        f"The {label} of the property {base_id}, as identified by the derivation term {derivation}."
    )
    assert served["description"].endswith("\n\n" + base["description"])
    for key in (
        "type",
        "x-optimade-type",
        "x-optimade-unit",
        "x-optimade-unit-definitions",
        "x-optimade-dimensions",
        "items",
    ):
        assert served.get(key) == base.get(key)
    (item,) = spec.layout
    assert item.field == unprefixed and item.dimensions == member_layout(spec.definition)[0].dimensions


def test_from_data_record_checks_the_generic_record() -> None:
    edge = RunEdge("input", "runs", "r1")
    generic = DataRecord.from_value(TEMPERATURE, "temperature", 300, product_of=[edge], id="t1")
    assert Temperature.from_data_record(generic) == Temperature(300.0, product_of=(edge,))
    assert Temperature.from_data_record(generic).id == "t1"
    with pytest.raises(ValueError, match=f"{STRESS_TENSOR}.* is not .*{TEMPERATURE}"):
        Temperature.from_data_record(DataRecord.from_value(STRESS_TENSOR, "stress", [0.0] * 6))
    derived = DerivedDataRecord.from_value(TEMPERATURE, RMSE, "temperature", 1.0)
    with pytest.raises(ValueError, match="got DerivedDataRecord"):
        Temperature.from_data_record(cast(Any, derived))
    with pytest.raises(ValueError, match="must not be None"):
        Temperature.from_data_record(DataRecord.from_value(TEMPERATURE, "temperature", None))


@dataclass(frozen=True)
class StressRmse(TypedRecord):
    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(
        STRESS_TENSOR, "_httk_stress_tensor_rmse", RMSE, "root-mean-square error"
    )

    stress_tensor_rmse: tuple[float, ...]
    product_of: Edges = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)


def test_derived_record_round_trip_and_projection() -> None:
    record = StressRmse.from_value([0, 0.5, 1, 0, 0, 0])
    assert record.stress_tensor_rmse == (0.0, 0.5, 1.0, 0.0, 0.0, 0.0) and record.definition_id == STRESS_TENSOR
    assert record.derivation == RMSE
    assert record.value == [0.0, 0.5, 1.0, 0.0, 0.0, 0.0]
    spec = StressRmse.__httk_typed_record__
    assert list(spec.definitions()) == ["_httk_stress_tensor_rmse"]
    projection = spec.projections()["_httk_stress_tensor_rmse"]
    assert projection.response(record) == record.value
    tag = ("scope", "stress_tensor_rmse", 1)
    assert _query(projection, "LENGTH =", 6) == ("cmp", ("count", tag), "=", ("const", 6))
    with pytest.raises(ValueError, match="length 5, expected 6|do not fill"):
        StressRmse((1.0,) * 5)
    with pytest.raises(TypeError, match="derived typed records are built with from_value"):
        StressRmse.from_data_record(DataRecord.from_value(STRESS_TENSOR, "stress", [0.0] * 6))


def test_declarations_are_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []

    def refuse(definition_id: str) -> PropertyDefinition:
        loads.append(definition_id)
        raise RuntimeError("registry touched")

    monkeypatch.setattr(typed_records, "load_property_definition", refuse)

    @dataclass(frozen=True)
    class Lazy(TypedRecord):
        __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(TEMPERATURE, "_httk_temperature")
        __httk_property_definitions__: ClassVar[Any] = __httk_typed_record__.definitions()
        __httk_stored_properties__: ClassVar[Any] = __httk_typed_record__.projections()

        temperature: float

    for mapping in (Lazy.__httk_property_definitions__, Lazy.__httk_stored_properties__):
        assert list(mapping) == ["_httk_temperature"] and len(mapping) == 1
    derived = TypedRecordSpec(STRESS_TENSOR, "_httk_stress_tensor_rmse", RMSE, "root-mean-square error")
    assert len(derived.definitions()) == 1 and list(derived.projections()) == ["_httk_stress_tensor_rmse"]
    assert loads == []
    with pytest.raises(RuntimeError, match="registry touched"):
        Lazy.__httk_property_definitions__["_httk_temperature"]
    with pytest.raises(KeyError):
        Lazy.__httk_stored_properties__["other"]

    monkeypatch.setattr(typed_records, "load_property_definition", load_property_definition)
    definitions = TypedRecordSpec(TEMPERATURE, "_httk_temperature").definitions()
    assert definitions["_httk_temperature"] is definitions["_httk_temperature"]
    assert definitions["_httk_temperature"].name == "_httk_temperature"


# --- Projections -----------------------------------------------------------------------------------------


class FakeScope:
    """Records ``field``/``scope`` calls as tuples; every ``scope`` call is a distinct numbered peer."""

    def __init__(self, tag: Any, counter: Callable[[], int]) -> None:
        self.tag = tag
        self._counter = counter

    def field(self, name: str) -> Any:
        return ("field", self.tag, name)

    def scope(self, name: str) -> "FakeScope":
        return FakeScope(("scope", name, self._counter()), self._counter)


class FakeContext(FakeScope):
    """A minimal recording QueryContext building a tuple expression tree."""

    def __init__(self) -> None:
        super().__init__("record", itertools.count(1).__next__)

    def constant(self, value: object) -> Any:
        return ("const", value)

    def always_true(self) -> Any:
        return ("true",)

    def always_false(self) -> Any:
        return ("false",)

    def compare(self, left: Any, operator: str, right: Any) -> Any:
        return ("cmp", left, operator, right)

    def equal(self, left: Any, right: Any) -> Any:
        return ("eq", left, right)

    def is_null(self, value: Any) -> Any:
        return ("null", value)

    def filtered(self, scope: FakeScope, predicate: Any) -> FakeScope:
        return FakeScope(("filtered", scope.tag, predicate), lambda: 0)

    def count(self, scope: FakeScope) -> Any:
        return ("count", scope.tag)

    def and_(self, *predicates: Any) -> Any:
        return ("and", *predicates)

    def or_(self, *predicates: Any) -> Any:
        return ("or", *predicates)

    def not_(self, predicate: Any) -> Any:
        return ("not", predicate)

    def when_known(self, known: Any, predicate: Any) -> Any:
        return ("when_known", known, predicate)


def _query(projection: StoredPropertyProjection, operator: str, literal: object = None) -> Any:
    assert projection.query is not None
    return projection.query(cast(Any, FakeContext()), operator, literal)


def _has(scope: int, field_name: str, value: object) -> Any:
    tag = ("scope", field_name, scope)
    matching = ("filtered", tag, ("eq", ("field", tag, "value"), ("const", value)))
    return ("cmp", ("count", matching), ">", ("const", 0))


def test_scalar_projection() -> None:
    projection = Temperature.__httk_typed_record__.projections()["_httk_temperature"]
    column = ("field", "record", "temperature")
    assert projection.response(Temperature(5.0)) == 5.0
    assert projection.sort is not None and projection.sort(cast(Any, FakeContext())) == column
    assert _query(projection, "IS_KNOWN") == ("not", ("null", column))
    assert _query(projection, "IS_UNKNOWN") == ("null", column)
    for operator in ("=", "!=", "<", "<=", ">", ">=", "CONTAINS", "STARTS", "ENDS"):
        assert _query(projection, operator, 7.5) == ("cmp", column, operator, ("const", 7.5))
    for operator in ("HAS_ALL", "LENGTH ="):
        with pytest.raises(QueryLiteralError):
            _query(projection, operator, 1)


def test_top_level_list_projection() -> None:
    projection = Stress.__httk_typed_record__.projections()["_httk_stress_tensor"]
    assert projection.response(Stress((1.0,) * 6)) == [1.0] * 6 and projection.sort is None
    assert _query(projection, "IS_KNOWN") == ("true",) and _query(projection, "IS_UNKNOWN") == ("false",)
    assert _query(projection, "HAS_ALL", (1.0, 2.0)) == (
        "and",
        _has(1, "stress_tensor", 1.0),
        _has(2, "stress_tensor", 2.0),
    )
    assert _query(projection, "HAS_ANY", [3.0]) == ("or", _has(1, "stress_tensor", 3.0))
    tag = ("scope", "stress_tensor", 1)
    value = ("field", tag, "value")
    others = ("and", ("not", ("eq", value, ("const", 1.0))), ("not", ("eq", value, ("const", 2.0))))
    assert _query(projection, "HAS_ONLY", (1.0, 2.0)) == (
        "cmp",
        ("count", ("filtered", tag, others)),
        "=",
        ("const", 0),
    )
    assert _query(projection, "LENGTH >=", 6) == ("cmp", ("count", tag), ">=", ("const", 6))
    for operator, literal in (("=", 1.0), ("CONTAINS", "x"), ("LENGTH =", 1.5), ("LENGTH =", True), ("HAS_ALL", 1.0)):
        with pytest.raises(QueryLiteralError):
            _query(projection, operator, literal)


def test_dictionary_projection_members() -> None:
    projection = Sample.__httk_typed_record__.projections()["_httk_sample"]
    record = Sample.from_value({**SAMPLE_VALUE, "tags": ["x"]})
    assert projection.response(record) == record.value and projection.sort is None
    assert _query(projection, "IS_KNOWN") == ("true",) and _query(projection, "IS_UNKNOWN") == ("false",)
    with pytest.raises(QueryLiteralError):
        _query(projection, "=", 1)
    members = projection.members
    assert list(members) == ["label", "weight", "count", "offset", "matrix", "tags", "values"]
    assert members["matrix"].response(record) == SAMPLE_VALUE["matrix"]
    assert members["tags"].response(record) == ["x"] and members["weight"].response(record) is None
    assert members["tags"].response(Sample.from_value(SAMPLE_VALUE)) is None

    # Scalar members query their column.
    assert _query(members["weight"], "<", 2) == ("cmp", ("field", "record", "weight"), "<", ("const", 2))
    assert _query(members["offset"], "IS_UNKNOWN") == ("null", ("field", "record", "offset"))

    # LENGTH is the outer length: rows are counted as rows * fixed inner size.
    matrix = ("scope", "matrix", 1)
    assert _query(members["matrix"], "LENGTH =", 2) == ("cmp", ("count", matrix), "=", ("const", 6))
    with pytest.raises(QueryLiteralError, match="one-dimensional"):
        _query(members["matrix"], "HAS_ANY", (1.0,))
    assert _query(members["values"], "HAS_ALL", (0.5,)) == ("and", _has(1, "values", 0.5))
    assert _query(members["values"], "IS_KNOWN") == ("true",)

    # Optional list members: known via <field>_present; every HAS/LENGTH predicate is wrapped.
    present = ("field", "record", "tags_present")
    known = ("eq", present, ("const", True))
    assert _query(members["tags"], "IS_KNOWN") == known
    assert _query(members["tags"], "IS_UNKNOWN") == ("eq", present, ("const", False))
    assert _query(members["tags"], "HAS_ANY", ("x", "y")) == (
        "when_known",
        known,
        ("or", _has(1, "tags", "x"), _has(2, "tags", "y")),
    )
    assert _query(members["tags"], "LENGTH <", 3) == (
        "when_known",
        known,
        ("cmp", ("count", ("scope", "tags", 1)), "<", ("const", 3)),
    )
    with pytest.raises(QueryLiteralError):
        _query(members["tags"], "STARTS", "x")


@dataclass(frozen=True)
class NullablePoints(TypedRecord):
    __httk_typed_record__: ClassVar[TypedRecordSpec] = TypedRecordSpec(NULLABLE_ID, "_httk_nullable_points")

    points: tuple[float, ...] | None
    product_of: Edges = ()
    id: Annotated[str | None, IdentitySkip(), Indexed()] = field(default=None, compare=False)
    immutable_id: Annotated[str | None, IdentitySkip(), Unique()] = field(default=None, compare=False)
    last_modified: Annotated[datetime.datetime | None, IdentitySkip()] = field(default=None, compare=False)


def test_required_nullable_list_member_is_not_always_known() -> None:
    assert NullablePoints.from_value({"points": None}).value == {"points": None}
    assert NullablePoints.from_value({"points": [1, 2]}).value == {"points": [1.0, 2.0]}
    projection = NullablePoints.__httk_typed_record__.projections()["_httk_nullable_points"]
    points = projection.members["points"]
    present = ("field", "record", "points_present")
    known = ("eq", present, ("const", True))
    assert _query(points, "IS_KNOWN") == known
    assert _query(points, "IS_UNKNOWN") == ("eq", present, ("const", False))
    assert _query(points, "HAS_ANY", (1.0,)) == ("when_known", known, ("or", _has(1, "points", 1.0)))
    assert _query(points, "LENGTH =", 0) == (
        "when_known",
        known,
        ("cmp", ("count", ("scope", "points", 1)), "=", ("const", 0)),
    )


def test_derived_title_keeps_acronyms() -> None:
    spec = TypedRecordSpec(NVE_ID, "_httk_nve_energy_drift_standard_error", STANDARD_ERROR, "standard error")
    assert spec.served_definition.title == "Standard error of NVE energy drift"
    assert typed_records._lower_first("Stress tensor") == "stress tensor"
