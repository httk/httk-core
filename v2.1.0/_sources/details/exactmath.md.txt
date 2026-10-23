# Exact math in detail

The functions in `httk.core.exactmath` provide exact and controlled-precision
arithmetic on their own: Fraction mode returns exact rationals or controlled rational
approximations, while Decimal input or `digits=` selects correctly rounded Decimal results.
Every value is computed with integer/rational arithmetic — there is no floating point anywhere in
the core computation, so results are platform-independent and deterministic by construction.

```python
from fractions import Fraction
from httk.core import exactmath
```

## Parsing values exactly

`any_to_fraction` converts numbers and strings into exact rationals. Decimal
strings are taken at their written value (unlike `float`s, which carry binary
rounding):

```python
exactmath.any_to_fraction("8.04")        # Fraction(201, 25)
exactmath.any_to_fraction("1/3")         # Fraction(1, 3)
```

A trailing parenthesized uncertainty (the common experimental notation) makes
the parser pick the **simplest rational inside the stated interval**:

```python
exactmath.any_to_fraction("0.33342(10)")  # Fraction(1, 3)
exactmath.string_to_val_and_delta("0.33342(10)")
# (Fraction(16671, 50000), Fraction(1, 10000))
```

Here `0.33342 ± 0.00010` brackets `1/3`, so `1/3` is returned. Without an
explicit uncertainty, `min_accuracy` (default `1/10000`) plays the same role;
pass `min_accuracy=None` to take a value exactly as written — including the
exact binary rational of a `float`:

```python
exactmath.any_to_fraction(0.1, min_accuracy=None)
# Fraction(3602879701896397, 36028797018963968)
```

## Best rationals and continued fractions

`best_rational_in_interval` returns the rational with the smallest denominator
in a closed interval — the workhorse behind the uncertainty parsing:

```python
exactmath.best_rational_in_interval("3.14", "3.15")   # Fraction(22, 7)
```

The continued-fraction helpers round-trip exactly:

```python
list(exactmath.get_continued_fraction(355, 113))      # [3, 7, 16]
exactmath.fraction_from_continued_fraction([3, 7, 16])  # Fraction(355, 113)
```

## Controlled-precision transcendentals (Fraction domain)

Given `Fraction`/`int`/`str` input (and no `digits=`), the transcendentals
return a `Fraction` within `prec` of the true value (default `prec` is very
fine; pass a `Fraction` to control it). With `limit=True` (the default) the
result's denominator is kept near `1/prec` rather than growing unboundedly:

```python
exactmath.sqrt(Fraction(2), prec=Fraction(1, 10**12))
# Fraction(1402795082585, 991925915511)   — (value)**2 is within 1e-12 of 2
```

Exact results are returned when they exist:

```python
exactmath.sqrt(Fraction(9, 4))               # Fraction(3, 2) — exact
exactmath.integer_sqrt(10**20)               # 10000000000 — exact integer sqrt
```

### Exact square roots as surds (`exact=True`)

For an irrational square root, `exact=True` overrides the output-domain rule entirely and returns
the value *symbolically* — as a {py:class}`~httk.core.vectors.surdvector.SurdScalar`, an element of
the squarefree-radical field, with **no** approximation:

```python
import fractions
from httk.core.vectors import SurdVector

root2 = exactmath.sqrt(fractions.Fraction(2), exact=True)
assert root2 * root2 == SurdVector(2)                       # squares back to exactly 2
assert exactmath.sqrt(fractions.Fraction(9, 4), exact=True) == SurdVector(fractions.Fraction(3, 2))
```

See {doc}`vectors` ("Exact radicals: `SurdVector`") for the field itself — exact Cartesian
crystallographic geometry, exact comparison, and the nested-radical limit.

## ScalarLike and VectorLike inputs

The public functions accept `ScalarLike` values (`int`, `float`, `str`, `Fraction`, `Decimal`,
`FracScalar`, or `SurdScalar`) and `VectorLike` values (vector backends/views, nested lists or
tuples, and optional NumPy arrays). Vectors are mapped elementwise and retain their shape. In
Fraction mode the result is a `FracVector`; Decimal mode returns nested tuples of `Decimal` values.
Decimal mode is promoted across the entire vector when any leaf is a `Decimal`, or when `digits=`
is supplied, with omitted `digits` using the active Decimal context precision.

Ordinary Fraction-mode calls on a genuinely irrational `SurdScalar` use its deterministic Fraction
hub: the value is approximated at the active Decimal context precision plus three guard digits.
Exact symbolic calls preserve the surd and never use this lossy conversion. Floats are embedded as
their exact binary `Fraction` value.

`exact=True` is available for `sqrt` and degree-mode `cos`, `sin`, `tan`, `asin`, `acos`, `atan`,
and `atan2`. Exact trigonometry requires `degrees=True`; cosine and sine values are exact for the
complete square-root angle set (multiples of 15° and 36°, with the corresponding sine/tangent
values where defined). Exact inverse functions return degree `Fraction`s. An unsupported angle or
value raises `ValueError`, rather than silently approximating. Vector exact results are
`SurdVector`-compatible and exact `atan2` accepts either two same-shaped vectors or scalar
broadcasting. `atan2` follows the usual quadrant convention.

`digits`, `rounding`, and `max_refinements` retain their Decimal-mode meanings for vectors. In
exact mode they are ignored, including invalid `digits` values.

The trigonometric functions accept `degrees=True` to interpret their argument
in degrees (`cos`, `sin`, ...) or to return degrees (`asin`, `acos`, `atan`,
`atan2`). `atan2` follows the quadrant conventions of {py:func}`math.atan2`:

```python
exactmath.atan2(Fraction(1), Fraction(0), degrees=True)   # Fraction(90, 1)
exactmath.atan2(Fraction(0), Fraction(-1), degrees=True)  # Fraction(180, 1)
```

`pi` returns a high-precision rational for π; note that for any requested
`prec` coarser than about 1e-13 it returns its precomputed high-precision
constant (more precise than asked — use `.limit_denominator()` on the result if
you want a small rational such as `355/113`):

```python
pi = exactmath.pi()
pi.limit_denominator(1000)               # Fraction(355, 113)
```

## Presentation and the `coerce=` keyword

By default results are presented view-neutrally in the input's type family (an `int`/`Fraction`
for int input, a `float` for float input, nested lists for list input, a native tuple view for
tuple input, a float64 numpy view for numpy input). The keyword-only `coerce=` overrides this,
following {func}`httk.core.coerce_view` semantics: the natural exact result stays recoverable
behind view presentations via `unwrap()`, and coercion failures propagate. `coerce="natural"`
returns the pre-presentation result unchanged. A caller that wants a plain, non-view value
applies {func}`httk.core.unview` to the returned presentation.

## Decimal mode

The same functions render a correctly-rounded {py:class}`decimal.Decimal` when
asked. The type of the result follows a single documented rule:

> The result is a `Decimal` iff any numeric input is a `Decimal` **or** `digits=`
> is passed; `Fraction`/`int`/`str` inputs otherwise get the exact `Fraction`
> behavior above.

A `Decimal` input therefore yields a `Decimal`, and `digits=` lets a
`Fraction`/`int` caller (or the argument-less `pi`) request one:

```python
import decimal
from fractions import Fraction

# Decimal input -> Decimal result:
assert isinstance(exactmath.sqrt(decimal.Decimal(2)), decimal.Decimal)
# digits= forces Decimal even from a Fraction input:
assert isinstance(exactmath.sqrt(Fraction(2), digits=10), decimal.Decimal)
# any Decimal argument promotes the whole result (mixed-argument promotion):
assert isinstance(exactmath.atan2(decimal.Decimal(1), Fraction(1)), decimal.Decimal)
```

`digits=` is the number of **significant digits** (default: the active
{py:func}`decimal.getcontext` precision, matching stdlib `Decimal`'s own model),
and `rounding=` selects `"half_even"` (the default — correctly rounded) or
`"down"` (correct truncation toward zero). The rendering uses Ziv's adaptive
strategy over the exact rational algorithms, so results are **correctly
rounded**:

```python
import decimal

# sqrt(2) correctly rounded to 30 significant digits, half-even:
assert exactmath.sqrt(decimal.Decimal(2), digits=30) == decimal.Decimal(
    "1.41421356237309504880168872421"
)
```

Exactly-representable results short-circuit through exact arithmetic — including
exact boundary cases — so, for example, the special-angle cosines/sines and
perfect-square roots come back exactly:

```python
import decimal

assert exactmath.cos(decimal.Decimal("60"), degrees=True) == decimal.Decimal("0.5")
assert exactmath.sin(decimal.Decimal("30"), degrees=True) == decimal.Decimal("0.5")
assert exactmath.sqrt(decimal.Decimal("2.25")) == decimal.Decimal("1.5")   # perfect square
```

### Correct rounding vs correct truncation

Truncation is deterministic and gets the same adaptive treatment, so it is
*correct* truncation of the true value — it has the same boundary hazard as
rounding, and the iteration disambiguates both modes identically. Consider a
value a hair above the 2-significant-digit boundary at `1.25` (constructed
exactly as `(1.25 + 1e-6)**2` so its square root is exactly `1.250001`):

```python
import decimal
from fractions import Fraction

boundary = (Fraction(125, 100) + Fraction(1, 10**6)) ** 2   # exact; sqrt is exactly 1.250001
assert exactmath.sqrt(boundary, digits=2, rounding="half_even") == decimal.Decimal("1.3")
assert exactmath.sqrt(boundary, digits=2, rounding="down") == decimal.Decimal("1.2")
```

Half-even rounds the value (just above `1.25`) up to `1.3`; truncation toward
zero gives `1.2`.

### Determinism and the context default

Results are deterministic: the same call twice is identical, and with `digits=`
given explicitly the result is independent of a changed `decimal` context. Only
when `digits=` is omitted does the active context precision apply:

```python
import decimal
from fractions import Fraction

# explicit digits= ignores the context precision entirely:
saved = decimal.getcontext().prec
decimal.getcontext().prec = 5
a = exactmath.sqrt(decimal.Decimal(2), digits=30)
decimal.getcontext().prec = 50
b = exactmath.sqrt(decimal.Decimal(2), digits=30)
decimal.getcontext().prec = saved
assert a == b

# without digits=, the context precision drives the significant-digit count:
decimal.getcontext().prec = 10
assert exactmath.sqrt(decimal.Decimal(2)) == decimal.Decimal("1.414213562")
decimal.getcontext().prec = saved
```

And `pi(digits=n)` gives π as a correctly-rounded `Decimal`:

```python
import decimal

assert exactmath.pi(digits=50) == decimal.Decimal(
    "3.1415926535897932384626433832795028841971693993751"
)
```

## Guaranteed termination

The adaptive rounding loop provably terminates, with no error
path. The table-maker's dilemma only bites when a function value sits *exactly on* a
rounding boundary, and boundaries are rational numbers. Classical number theory rules
that out for every function here once the exact special cases are handled: by the
Lindemann–Weierstrass theorem, `exp`, `log`, and radian-mode trigonometry take
transcendental values at nonzero rational arguments; by Niven's theorem, degree-mode
trigonometry takes rational values only at the tabulated special angles (all handled
exactly); square roots of non-perfect-square rationals are irrational (perfect squares
are detected exactly); and whether `log(x, base)` is rational is a *finite exact
decision* — `log_base(x) = p/q` requires `x**q == base**p`, and `q` is bounded by the
largest prime exponent of `base`, so all candidates are checked with exact integer
arithmetic:

```python
import decimal
from httk.core import exactmath

# log_4(8) = 3/2 exactly: at one significant digit this is a perfect rounding tie,
# resolved by exact arithmetic — half-even rounds to 2, truncation gives 1.
assert exactmath.log(decimal.Decimal(8), decimal.Decimal(4), digits=1) == decimal.Decimal("2")
assert exactmath.log(decimal.Decimal(8), decimal.Decimal(4), digits=1, rounding="down") == decimal.Decimal("1")

# Exact special values survive truncation mode untouched:
assert exactmath.asin(decimal.Decimal("0.5"), degrees=True, digits=4, rounding="down") == decimal.Decimal("30")
```

Every remaining value is therefore provably irrational, hence never exactly on a
boundary, and the interval refinement always disambiguates in finitely many steps —
deterministically, on every platform.

### Bounded time without losing determinism

Correct rounding has input-dependent cost: a value constructed to lie extremely close to a
rounding boundary (e.g. `sqrt((1.25 + 1e-40)**2)` at two digits) forces many refinements
before the interval clears the boundary. When a hard time bound matters more than
correctness in that vanishing sliver, pass `max_refinements=k`: at most `k` refinements
are performed, and if still ambiguous the *approximation itself* is rounded — the
`StrictMath` philosophy of letting a frozen, exact algorithm define the function. The
result is then correctly rounded unless the true value lies within `10**-(digits+3+4k)`
of a boundary, in which case it is the deterministic rounding of the deterministic
approximant — off by at most one unit in the last place, and identical on every platform,
every time:

```python
import decimal
import fractions
from httk.core import exactmath

boundary = fractions.Fraction(125, 100) + fractions.Fraction(1, 10**40)
x = boundary * boundary
assert exactmath.sqrt(x, digits=2) == decimal.Decimal("1.3")     # unbounded: correct
fast = exactmath.sqrt(x, digits=2, max_refinements=0)            # bounded: one pass
assert fast == exactmath.sqrt(x, digits=2, max_refinements=0)    # ... and repeatable
```

The default (`max_refinements=None`) keeps the guaranteed-correct behavior above.

## Using it with FracVector

`FracVector`'s element-wise transcendental methods call these functions on each
element, so everything above applies vector-wide:

```python
from httk.core.vectors import FracVector

v = FracVector([["9/4", "1/4"]])
v.sqrt().to_fractions()                  # [[Fraction(3, 2), Fraction(1, 2)]] — exact
```

See {doc}`vectors` for the vector library itself and the Vector view family.
