"""Tests for the typed-record layout layer (member layouts, flattening and reassembly)."""

from typing import Any

import pytest

from httk.core import PropertyDefinition, load_property_definition
from httk.core.definition_ids import ATOMIC_FORCE, STRESS_TENSOR, TEMPERATURE
from httk.core.typed_records import MemberLayout, _flatten_value, _reassemble_value, member_layout


def _leaf(kind: str, nullable: bool = False) -> dict[str, Any]:
    json_type = {"float": "number", "integer": "integer", "string": "string", "boolean": "boolean"}[kind]
    return {"x-optimade-type": kind, "type": [json_type, "null"] if nullable else [json_type]}


def _list(items: dict[str, Any], name: str, size: int | None = None, nullable: bool = False) -> dict[str, Any]:
    return {
        "x-optimade-type": "list",
        "type": ["array", "null"] if nullable else ["array"],
        "x-optimade-dimensions": {"names": [name], "sizes": [size]},
        "items": items,
    }


def _definition(name: str, level: dict[str, Any]) -> PropertyDefinition:
    document = {"$id": f"https://example.org/defs/{name}", "description": name, **level}
    if document["x-optimade-type"] in ("dictionary", "list"):
        document["type"] = [document["type"][0], "null"]
    return PropertyDefinition.from_optimade(name, document)


def _dictionary(name: str, members: dict[str, Any], required: list[str]) -> PropertyDefinition:
    return _definition(
        name, {"x-optimade-type": "dictionary", "type": ["object"], "properties": members, "required": required}
    )


def _vector(name: str, kind: str = "float") -> dict[str, Any]:
    return _list(_leaf(kind), name)


PHASE_DIAGRAM = _dictionary(
    "convex_hull_phase_diagram",
    {
        "elements": _vector("_httk_dim_elements", "string"),
        "phase_ids": _vector("_httk_dim_phases", "string"),
        "compositions": _list(_vector("_httk_dim_elements"), "_httk_dim_phases"),
        "energies_per_atom": _vector("_httk_dim_phases"),
        "stable": _vector("_httk_dim_phases", "boolean"),
        "tolerance": _leaf("float"),
    },
    ["elements", "compositions", "energies_per_atom", "stable", "tolerance"],
)

ISF = _dictionary(
    "intermediate_scattering_function",
    {
        "lag_times": _vector("_httk_dim_lags"),
        "wavevectors": _list(_list(_leaf("float"), "dim_spatial", 3), "_httk_dim_wavevectors"),
        "real": _list(_vector("_httk_dim_wavevectors"), "_httk_dim_lags"),
        "origin_counts": _vector("_httk_dim_lags", "integer"),
    },
    ["lag_times", "wavevectors", "real"],
)

MSD = _dictionary(
    "mean_squared_displacement",
    {
        "lag_times": _vector("_httk_dim_lags"),
        "msd": _list(_list(_list(_leaf("float"), "dim_spatial", 3), "dim_spatial", 3), "_httk_dim_lags"),
    },
    ["lag_times", "msd"],
)

STEINHARDT = _dictionary(
    "steinhardt_bond_order",
    {
        "degree": _leaf("integer"),
        "global_order": _leaf("float", nullable=True),
        "local_orders": _list(_leaf("float", nullable=True), "_httk_dim_atoms"),
    },
    ["degree", "global_order", "local_orders"],
)

ENERGY_ERRORS = _dictionary(
    "energy_prediction_errors",
    {
        "weighting": {**_leaf("string"), "enum": ["configuration", "atom"]},
        "offset_per_atom": _leaf("float", nullable=True),
        "count": _leaf("integer"),
        "residuals": _vector("_httk_dim_configurations"),
        "mean_square": _leaf("float"),
    },
    ["weighting", "offset_per_atom", "count", "residuals"],
)

ELASTIC = _definition("elastic_tensor", _list(_list(_leaf("float"), "_httk_dim_voigt", 6), "_httk_dim_voigt", 6))


def _roundtrip(definition: PropertyDefinition, value: Any) -> dict[str, Any]:
    layouts = member_layout(definition)
    flats = _flatten_value(layouts, value)
    restored = _reassemble_value(layouts, flats)
    assert restored == value
    definition.check(restored)
    return flats


def _summary(layouts: tuple[MemberLayout, ...]) -> list[tuple[str, str, tuple[tuple[str, int | None], ...]]]:
    return [(layout.field, layout.fulltype, layout.dimensions) for layout in layouts]


def test_phase_diagram_layout_and_roundtrip() -> None:
    layouts = member_layout(PHASE_DIAGRAM)
    assert _summary(layouts)[:3] == [
        ("elements", "list of string", (("_httk_dim_elements", None),)),
        ("phase_ids", "list of string", (("_httk_dim_phases", None),)),
        ("compositions", "list of list of float", (("_httk_dim_phases", None), ("_httk_dim_elements", None))),
    ]
    assert [layout.required for layout in layouts] == [True, False, True, True, True, True]
    assert layouts[1].path == ("phase_ids",) and layouts[4].leaf == "boolean"
    value = {
        "elements": ["Li", "O"],
        "compositions": [[1.0, 0.0], [0.4, 0.6], [0.0, 1.0]],
        "energies_per_atom": [0.0, -2.5, 0.0],
        "stable": [True, True, False],
        "tolerance": 1e-8,
    }
    flats = _roundtrip(PHASE_DIAGRAM, value)
    assert flats["compositions"] == (1.0, 0.0, 0.4, 0.6, 0.0, 1.0)
    assert flats["phase_ids"] is None and flats["stable"] == (True, True, False)
    _roundtrip(PHASE_DIAGRAM, {**value, "phase_ids": ["a", "b", "c"]})
    _roundtrip(
        PHASE_DIAGRAM,
        {"elements": ["Li"], "compositions": [], "energies_per_atom": [], "stable": [], "tolerance": 0.0},
    )


def test_isf_roundtrip_with_and_without_wavevectors() -> None:
    assert _summary(member_layout(ISF))[2] == (
        "real",
        "list of list of float",
        (("_httk_dim_lags", None), ("_httk_dim_wavevectors", None)),
    )
    value = {
        "lag_times": [0.0, 1.0],
        "wavevectors": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "real": [[1.0, 1.0, 1.0], [0.5, 0.25, 0.125]],
        "origin_counts": [10, 9],
    }
    assert _roundtrip(ISF, value)["wavevectors"] == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    empty = {"lag_times": [0.0, 1.0, 2.0], "wavevectors": [], "real": [[], [], []]}
    assert _roundtrip(ISF, empty)["real"] == ()
    _roundtrip(ISF, {"lag_times": [], "wavevectors": [], "real": []})


def test_three_dimensional_member() -> None:
    assert member_layout(MSD)[1].dimensions == (("_httk_dim_lags", None), ("dim_spatial", 3), ("dim_spatial", 3))
    assert member_layout(MSD)[1].fulltype == "list of list of list of float"
    tensors = [[[float(lag * 9 + 3 * row + col) for col in range(3)] for row in range(3)] for lag in range(2)]
    flats = _roundtrip(MSD, {"lag_times": [0.0, 1.0], "msd": tensors})
    assert flats["msd"] == tuple(float(index) for index in range(18))


def test_nullable_elements_and_scalars() -> None:
    layouts = {layout.field: layout for layout in member_layout(STEINHARDT)}
    assert layouts["global_order"].nullable and not layouts["global_order"].element_nullable
    assert layouts["local_orders"].element_nullable and not layouts["local_orders"].nullable
    flats = _roundtrip(STEINHARDT, {"degree": 6, "global_order": None, "local_orders": [0.5, None, 0.25]})
    assert flats == {"degree": 6, "global_order": None, "local_orders": (0.5, None, 0.25)}


def test_optional_member_omission_and_required_none() -> None:
    layouts = member_layout(ENERGY_ERRORS)
    assert [layout.field for layout in layouts if not layout.required] == ["mean_square"]
    value = {"weighting": "atom", "offset_per_atom": None, "count": 3, "residuals": [0.1, -0.2, 0.0]}
    flats = _roundtrip(ENERGY_ERRORS, value)
    assert flats["mean_square"] is None and flats["count"] == 3
    restored = _reassemble_value(layouts, flats)
    assert "offset_per_atom" in restored and "mean_square" not in restored
    _roundtrip(ENERGY_ERRORS, {**value, "mean_square": 0.25})


def test_top_level_list_and_core_definitions() -> None:
    (layout,) = member_layout(ELASTIC)
    assert (layout.field, layout.path, layout.fulltype, layout.required, layout.nullable) == (
        "elastic_tensor",
        (),
        "list of list of float",
        True,
        True,
    )
    assert layout.dimensions == (("_httk_dim_voigt", 6), ("_httk_dim_voigt", 6))
    tensor = [[float(6 * row + col) for col in range(6)] for row in range(6)]
    assert len(_roundtrip(ELASTIC, tensor)["elastic_tensor"]) == 36
    stress = load_property_definition(STRESS_TENSOR)
    assert _summary(member_layout(stress)) == [("stress_tensor", "list of float", (("_httk_dim_voigt", 6),))]
    _roundtrip(stress, [1.0, 2.0, 3.0, 0.0, 0.0, 0.0])
    _roundtrip(load_property_definition(ATOMIC_FORCE), [0.0, 0.5, -0.5])
    temperature = load_property_definition(TEMPERATURE)
    (scalar,) = member_layout(temperature)
    assert (scalar.fulltype, scalar.leaf, scalar.dimensions, scalar.element_nullable) == ("float", "float", (), False)
    assert _roundtrip(temperature, 300.0) == {"temperature": 300.0}


def test_multi_entry_top_level_dimension_declaration() -> None:
    inner = {"x-optimade-type": "list", "type": ["array"], "items": _leaf("float")}
    level = {**inner, "items": inner, "x-optimade-dimensions": {"names": ["rows", "cols"], "sizes": [2, 3]}}
    (layout,) = member_layout(_definition("matrix", level))
    assert layout.dimensions == (("rows", 2), ("cols", 3))


def test_flatten_rejections() -> None:
    layouts = member_layout(PHASE_DIAGRAM)
    good = {"elements": ["Li", "O"], "compositions": [[1.0, 0.0]], "energies_per_atom": [0.0], "stable": [True]}
    with pytest.raises(ValueError, match="ragged"):
        _flatten_value(layouts, {**good, "tolerance": 0.0, "compositions": [[1.0, 0.0], [1.0]]})
    with pytest.raises(ValueError, match="divide"):
        _flatten_value(layouts, {**good, "tolerance": 0.0, "compositions": [[1.0, 0.0, 0.0]]})
    with pytest.raises(ValueError, match="do not fill"):
        _flatten_value(layouts, {**good, "tolerance": 0.0, "compositions": [[1.0, 0.0, 0.0, 1.0]]})
    with pytest.raises(ValueError, match="non-list"):
        _flatten_value(layouts, {**good, "tolerance": 0.0, "compositions": [1.0]})
    with pytest.raises(ValueError, match="required"):
        _flatten_value(layouts, good)
    with pytest.raises(ValueError, match="unknown"):
        _flatten_value(layouts, {**good, "tolerance": 0.0, "extra": 1})
    with pytest.raises(ValueError, match="None"):
        _flatten_value(layouts, None)
    with pytest.raises(ValueError, match="dictionary"):
        _flatten_value(layouts, [1.0])
    with pytest.raises(ValueError, match="divide"):
        _reassemble_value(member_layout(ISF), {"lag_times": None, "wavevectors": (1.0, 2.0), "real": None})
    # Three empty rows with no sibling naming their count would come back as no rows.
    lone = _dictionary("lone", {"wavevectors": _vector("k"), "real": _list(_vector("k"), "lags")}, ["real"])
    with pytest.raises(ValueError, match="reassemble as"):
        _flatten_value(member_layout(lone), {"wavevectors": [], "real": [[], [], []]})
    assert _reassemble_value(member_layout(lone), {"wavevectors": (), "real": ()}) == {"wavevectors": [], "real": []}
    with pytest.raises(ValueError, match="cannot reassemble"):
        _flatten_value(member_layout(lone), {"real": [[1.0]]})


@pytest.mark.parametrize(
    ("definition", "match"),
    [
        (_dictionary("stamp", {"when": {"x-optimade-type": "timestamp", "type": ["string"]}}, []), "leaf type"),
        (_dictionary("nested", {"inner": _dictionary("x", {}, []).as_optimade()}, []), "nested dictionary"),
        (_definition("lod", _list(_dictionary("x", {}, []).as_optimade(), "n")), "list of dictionaries"),
        (_dictionary("undimensioned", {"a": {**_vector("n"), "x-optimade-dimensions": {}}}, []), "dimension"),
        (
            _dictionary("nullrows", {"a": _list(_list(_leaf("float"), "m", 3, nullable=True), "n")}, []),
            "nullable inner",
        ),
        (_dictionary("unsupplied", {"a": _list(_vector("m"), "n")}, []), "no sibling"),
        (_dictionary("square", {"a": _list(_vector("n"), "n")}, []), "no sibling"),
        (_definition("toplevel", _list(_vector("m"), "n", 3)), "no sibling"),
        (_dictionary("reserved", {"value": _leaf("float")}, []), "reserved"),
        (_dictionary("definition", {"definition_id": _leaf("string")}, []), "reserved"),
        (_dictionary("derived", {"derivation": _leaf("string")}, []), "reserved"),
        (_dictionary("lineage", {"logical_id": _leaf("string")}, []), "reserved"),
        (_dictionary("stamped", {"store_timestamp": _leaf("integer")}, []), "reserved"),
        (_dictionary("present", {"x_present": _leaf("float")}, []), "reserved"),
        (_dictionary("exact", {"x": _leaf("float"), "x_exact": _leaf("string")}, []), "reserved"),
        (_definition("id", _leaf("float")), "reserved"),
    ],
)
def test_layout_rejections(definition: PropertyDefinition, match: str) -> None:
    with pytest.raises(ValueError, match=match) as excinfo:
        member_layout(definition)
    assert definition.name in str(excinfo.value)
