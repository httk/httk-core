"""Tests for the OPTIMADE unit engine in httk.core.units."""

import importlib.resources
import json
from fractions import Fraction

import pytest

from httk.core.units import Conversion, UnitRegistry, default_registry

R = default_registry()


@pytest.mark.parametrize(
    "expression",
    ["GPa", "ps", "THz", "angstrom^3", "angstrom^-3*eV", "K^-1*W*m^-1", "Pa*s", "m^2*s^-1", "A^-1*kg*m^2*s^-3"],
)
def test_parse_accepts_spec_grammar(expression):
    assert R.parse(expression)


@pytest.mark.parametrize(
    "expression", ["m/s", "m s", "m*s ", "(m)", "m*K", "m*m", "m^0", "m^+2", "m^", "m**s", "", "*m", "G^2", "G", "Gx"]
)
def test_parse_rejects_invalid_expressions(expression):
    with pytest.raises(ValueError):
        R.parse(expression)


def test_parse_ambiguous_prefix_split_raises():
    with pytest.raises(ValueError, match="ambiguous"):
        R.parse("dau")


@pytest.mark.parametrize(
    ("expression", "parsed"),
    [
        ("Pa", (None, "Pa", 1)),
        ("m", (None, "m", 1)),
        ("T", (None, "T", 1)),
        ("h", (None, "h", 1)),
        ("fs", ("f", "s", 1)),
        ("GPa", ("G", "Pa", 1)),
        ("m^1", (None, "m", 1)),
        ("angstrom^-3", (None, "angstrom", -3)),
    ],
)
def test_whole_symbol_wins_over_prefix_split(expression, parsed):
    assert R.parse(expression) == (parsed,)


def test_definition_lookup():
    assert R.definition("Pa").kind == "unit"
    assert R.definition("G").kind == "prefix"
    assert R.definition("e").definition_id.endswith("/constants/codata/2018/electromagnetic/elementarycharge")
    with pytest.raises(TypeError):
        R.definition("m").document["symbol"] = "x"  # type: ignore[index]
    with pytest.raises(KeyError):
        R.definition("Gx")


@pytest.mark.parametrize(
    ("source", "target", "factor", "approximate"),
    [
        ("GPa", "Pa", Fraction(10**9), False),
        ("angstrom^-3*eV", "GPa", Fraction(1602176634, 10**7), True),
        ("bar", "GPa", Fraction(1, 10**4), False),
        ("ps", "fs", Fraction(1000), False),
        ("K^-1*angstrom^-1*eV*ps^-1", "K^-1*W*m^-1", Fraction(1602176634, 10**6), True),
        ("angstrom^-3*eV*ps", "Pa*s", Fraction(1602176634, 10**10), True),
        ("angstrom^2*ps^-1", "m^2*s^-1", Fraction(1, 10**8), False),
        ("dimensionless", "dimensionless", Fraction(1), False),
    ],
)
def test_exact_factors(source, target, factor, approximate):
    assert R.factor(source, target) == Conversion(factor, approximate)


def test_dimension():
    assert R.dimension("K^-1*W*m^-1") == R.dimension(R.canonical("angstrom^-1*eV*K^-1*ps^-1"))
    assert R.dimension("GPa") == {"kg": 1, "m": -1, "s": -2}
    assert R.dimension("dimensionless") == {}
    assert R.dimension("m*s^-1") == R.dimension("Hz*m")


def test_dimension_mismatch_and_inapplicable_raise():
    with pytest.raises(ValueError, match="'eV'"):
        R.factor("eV", "GPa")
    with pytest.raises(ValueError):
        R.dimension("inapplicable")


def test_convert_nested_values():
    assert R.convert([[1, 2.5], (3,)], "GPa", "Pa") == [[1e9, 2.5e9], [3e9]]
    assert R.convert(1.5, "bar", "GPa") == 1.5e-4
    with pytest.raises(TypeError):
        R.convert("1", "GPa", "Pa")


def test_canonical():
    assert R.canonical("m*K") == "K*m"
    assert R.canonical("m^1") == "m"
    assert R.canonical("s^-1*angstrom^2") == "angstrom^2*s^-1"
    with pytest.raises(ValueError):
        R.canonical("m*m")


def test_every_vendored_symbol_resolves_except_known_broken_upstream():
    root = importlib.resources.files("httk.registry.schemas.core") / "units"
    index = json.loads((root / "index.json").read_text())
    assert len(index) == 98
    failures = set()
    for entry in index:
        document = json.loads((root / entry["path"]).read_text())
        symbol = document["symbol"]
        if document["x-optimade-definition"]["kind"] == "prefix":
            continue
        try:
            R.dimension(symbol)
        except ValueError:
            failures.add(symbol)
    # knot writes 'ms^-1' (millisecond) for m*s^-1, pc's relation lacks its expression, degC is affine.
    assert failures == {"degC", "knot", "pc"}


def test_relation_cycles_and_affine_units_raise():
    def unit(symbol, expression):
        return {
            "$id": f"urn:{symbol}",
            "symbol": symbol,
            "x-optimade-definition": {"kind": "unit"},
            "defining-relation": {"base-units": [], "base-units-expression": expression},
        }

    registry = UnitRegistry([unit("x", "y"), unit("y", "x")])
    with pytest.raises(ValueError, match="cyclic"):
        registry.dimension("x")
    with pytest.raises(ValueError, match="affine"):
        R.dimension("degC")


def test_definitions_lists_prefixes_before_their_units():
    assert [(d.kind, d.symbol) for d in R.definitions("GPa")] == [("prefix", "G"), ("unit", "Pa")]
    assert [d.symbol for d in R.definitions("K^-1*W*m^-1")] == ["K", "W", "m"]
    assert R.definitions("dimensionless") == ()


def test_definitions_are_distinct_and_strictly_parsed():
    assert [(d.kind, d.symbol) for d in R.definitions("mm*ms")] == [("prefix", "m"), ("unit", "m"), ("unit", "s")]
    with pytest.raises(ValueError):
        R.definitions("m*K")


@pytest.mark.parametrize("value", [True, [1.0, [False]], (2, None)])
def test_apply_rejects_booleans_and_non_numbers(value):
    with pytest.raises(TypeError):
        R.factor("GPa", "Pa").apply(value)
    numpy = pytest.importorskip("numpy")
    with pytest.raises(TypeError):
        R.factor("GPa", "Pa").apply([numpy.True_])
