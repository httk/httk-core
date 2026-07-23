# Exact math on rationals

The functions in `httk.core.vectors.fracmath` do exact and controlled-precision
arithmetic on plain stdlib {py:class}`fractions.Fraction` values. They are fully
usable **without** `FracVector`: `FracVector`'s element-wise methods (`sqrt`,
`cos`, `exp`, ...) delegate here, but nothing stops you from calling these
functions directly on `Fraction`s in your own code. All results are `Fraction`s
— there is no floating point anywhere in the computation.

```python
from fractions import Fraction
from httk.core.vectors import fracmath
```

## Parsing values exactly

`any_to_fraction` converts numbers and strings into exact rationals. Decimal
strings are taken at their written value (unlike `float`s, which carry binary
rounding):

```python
fracmath.any_to_fraction("8.04")        # Fraction(201, 25)
fracmath.any_to_fraction("1/3")         # Fraction(1, 3)
```

A trailing parenthesized uncertainty (the common experimental notation) makes
the parser pick the **simplest rational inside the stated interval**:

```python
fracmath.any_to_fraction("0.33342(10)")  # Fraction(1, 3)
fracmath.string_to_val_and_delta("0.33342(10)")
# (Fraction(16671, 50000), Fraction(1, 10000))
```

Here `0.33342 ± 0.00010` brackets `1/3`, so `1/3` is returned. Without an
explicit uncertainty, `min_accuracy` (default `1/10000`) plays the same role;
pass `min_accuracy=None` to take a value exactly as written — including the
exact binary rational of a `float`:

```python
fracmath.any_to_fraction(0.1, min_accuracy=None)
# Fraction(3602879701896397, 36028797018963968)
```

## Best rationals and continued fractions

`best_rational_in_interval` returns the rational with the smallest denominator
in a closed interval — the workhorse behind the uncertainty parsing:

```python
fracmath.best_rational_in_interval("3.14", "3.15")   # Fraction(22, 7)
```

The continued-fraction helpers round-trip exactly:

```python
list(fracmath.get_continued_fraction(355, 113))      # [3, 7, 16]
fracmath.fraction_from_continued_fraction([3, 7, 16])  # Fraction(355, 113)
```

## Controlled-precision transcendentals

The `frac_*` functions return a rational within `prec` of the true value
(default `prec` is very fine; pass a `Fraction` to control it). With
`limit=True` (the default) the result's denominator is kept near `1/prec`
rather than growing unboundedly:

```python
fracmath.frac_sqrt(Fraction(2), prec=Fraction(1, 10**12))
# Fraction(1402795082585, 991925915511)   — (value)**2 is within 1e-12 of 2
```

Exact results are returned when they exist:

```python
fracmath.frac_sqrt(Fraction(9, 4))               # Fraction(3, 2) — exact
fracmath.integer_sqrt(10**20)                    # 10000000000 — exact integer sqrt
fracmath.frac_cos(Fraction(60), degrees=True)    # Fraction(1, 2) — exact
fracmath.frac_sin(Fraction(30), degrees=True)    # Fraction(1, 2) — exact
```

The trigonometric functions accept `degrees=True` to interpret their argument
in degrees (`frac_cos`, `frac_sin`, ...) or to return degrees (`frac_asin`,
`frac_acos`, `frac_atan`, `frac_atan2`). `frac_atan2` follows the quadrant
conventions of {py:func}`math.atan2`:

```python
fracmath.frac_atan2(Fraction(1), Fraction(0), degrees=True)   # Fraction(90, 1)
fracmath.frac_atan2(Fraction(0), Fraction(-1), degrees=True)  # Fraction(180, 1)
```

`frac_pi` returns a high-precision rational for π; note that for any requested
`prec` coarser than about 1e-13 it returns its precomputed high-precision
constant (more precise than asked — use `.limit_denominator()` on the result if
you want a small rational such as `355/113`):

```python
pi = fracmath.frac_pi()
pi.limit_denominator(1000)               # Fraction(355, 113)
```

## Using it with FracVector

`FracVector`'s element-wise transcendental methods call these functions on each
element, so everything above applies vector-wide:

```python
from httk.core import FracVector

v = FracVector.create([["9/4", "1/4"]])
v.sqrt().to_fractions()                  # [[Fraction(3, 2), Fraction(1, 2)]] — exact
```

See {doc}`vectors` for the vector library itself and the Vector view family.
