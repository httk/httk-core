# Units

*httk₂* values never carry unit strings. Every recorded value is in the unit
fixed by its OPTIMADE property definition (`x-optimade-unit`); a unit appears
only when converting at an input or output boundary. `httk.core.units` is a
stdlib-only engine for OPTIMADE Compound Unit Expressions, working on the unit,
prefix and constant definitions vendored under `httk.registry.schemas.core`.
The core property IRIs are in `httk.core.definition_ids`.

```python
from fractions import Fraction

from httk.core.units import default_registry

units = default_registry()
assert units.factor("bar", "GPa").factor == Fraction(1, 10000)
assert units.convert([1, 2], "bar", "GPa") == [0.0001, 0.0002]
assert units.canonical("s*m") == "m*s"
```

## Grammar

- Factors are joined with `*`; there is no `/`: write `m*s^-1`.
- Powers are integers (`angstrom^3`); symbols may not repeat.
- `parse` requires symbols in code-point order (so `m*s`, not `s*m`);
  `canonical` sorts for you.
- A prefix is a separate document (`G` + `Pa`). A whole symbol always wins over
  a prefix split; a split that stays ambiguous raises `ValueError`.
- `dimensionless` is the empty unit; `inapplicable` is not a unit.

## Approximate relations and limits

`factor` returns a `Conversion` with exact `Fraction` factors and an
`approximate` flag. It is set when an upstream relation is itself approximate:
`eV` is only approximately related to `e*V` upstream, yet the factor is still an
exact rational.

```python
assert default_registry().factor("eV", "J").approximate
assert not default_registry().factor("bar", "Pa").approximate
```

Known limits of the upstream definitions: `kg` is a base unit and `g` is
undefined; affine units such as `degC` parse but are rejected by `dimension`,
`factor` and `convert`; `knot` and `pc` cannot be resolved; and the upstream
relation defects reported for `are`, `barn` and `rem` are not worked around
(`are` and `barn` are not vendored).

## Property definitions

`PropertyDefinition.from_simple(..., unit="GPa")` parses the unit strictly
(invalid or unknown symbols raise `ValueError`) and embeds the vendored
definition documents of every distinct prefix, unit and constant symbol, in
order of first appearance and without `$schema`, as
`x-optimade-unit-definitions`. `dimensionless` and `inapplicable` embed nothing.

```python
from httk.core import PropertyDefinition

pressure = PropertyDefinition.from_simple(
    "_httk_demo_pressure", fulltype="float", unit="GPa", description="Pressure."
)
assert [d["symbol"] for d in pressure.unit_definitions] == ["G", "Pa"]
```

`PropertyDefinition.check(value)` is a stdlib structural check of a JSON-like
value (null only where allowed, types, finite floats, fixed list sizes, nested
dictionary properties). It raises `ValueError` naming the definition and the
path of the offending item:

```python
from httk.core import load_property_definition
from httk.core.definition_ids import STRESS_TENSOR

stress = load_property_definition(STRESS_TENSOR)
stress.check([1.0, 2.0, 3.0, 0.0, 0.0, 0.0])
try:
    stress.check([1.0, 2.0, "x", 0.0, 0.0, 0.0])
except ValueError as error:
    assert "stress_tensor[2]" in str(error)
else:
    raise AssertionError("expected ValueError")
```
