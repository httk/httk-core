# Vectors

This page documents the exact-rational vector library in `httk.core.vectors` and the Vector
backend/view family that lets the same tensor data be viewed as the exact representation, as
plain nested sequences, or (optionally) as numpy arrays.

## Exact rational arithmetic

`FracVector` is an immutable N-dimensional tensor stored as a nested tuple of integer nominators
over a single shared integer denominator. All arithmetic is exact — there is no floating-point
rounding anywhere — which makes it well suited to crystallography, where cell vectors and reduced
coordinates are naturally rational.

```python
from httk.core import FracVector

cell = FracVector.create([["8.04", "0.0", "0.0"],
                          ["0.0", "3.72", "0.0"],
                          ["0.0", "0.0", "7.38"]])

# Exact reciprocal cell (rows are the reciprocal vectors, without the 2*pi factor):
recip = cell.reciprocal()
assert recip.noms == ((3431700, 0, 0), (0, 7416900, 0), (0, 0, 3738600))
assert recip.denom == 27590868
```

The raw representation is always a nested tuple of integer nominators (`.noms`) over one shared
integer denominator (`.denom`); the tensor is `(1/denom) * noms`. Equality (`==`) compares
*numerical* value, so the denominator need not match:

```python
from httk.core import FracVector

assert FracVector([[1]], 2) == FracVector([[2]], 4)   # both are 1/2
```

### Creation from every numeric type

`FracVector.create(...)` accepts nested lists/tuples whose leaves are any of the following:

| leaf type            | example                          | becomes                       |
| -------------------- | -------------------------------- | ----------------------------- |
| `int`                | `1`                              | `1`                           |
| `str` (decimal)      | `"8.04"`                         | `804/100` (at stated digits)  |
| `str` (fraction)     | `"2/3"`                          | `2/3`                         |
| `str` (uncertainty)  | `"0.33342(10)"`                  | best rational in the interval |
| `decimal.Decimal`    | `Decimal("2.125")`               | `17/8` (exact)                |
| `fractions.Fraction` | `Fraction(2, 3)`                 | `2/3` (exact)                 |
| `float`              | `8.04`                           | the exact **binary** rational |

```python
import decimal
import fractions
from httk.core import FracVector

# int, str, Decimal and Fraction leaves all land on their exact rational value:
assert FracVector.create([decimal.Decimal("0.25"), decimal.Decimal("2.125")]).to_tuple() == (8, (2, 17))
assert FracVector.create([fractions.Fraction(2, 3), fractions.Fraction(3, 4)]).to_tuple() == (12, (8, 9))
assert FracVector.create("2/3").to_fraction() == fractions.Fraction(2, 3)
```

String input is parsed for significant digits, so a written decimal is taken at its stated
precision (and an explicit standard deviation is honored) rather than as an exact binary float:

```python
import fractions
from httk.core import FracVector

FracVector.create("0.33")                      # -> 33/100  (0.33 assumed to mean 0.3300)
FracVector.create("0.3333")                    # -> 1/3     (enough digits to imply 1/3)
FracVector.create("0.33", min_accuracy=None)   # -> 33/100, converted exactly
FracVector.create(["0.33342(10)"])             # -> 1/3, using the explicit standard deviation

assert FracVector.create("0.33").to_fraction() == fractions.Fraction(33, 100)
assert FracVector.create("0.3333").to_fraction() == fractions.Fraction(1, 3)
assert FracVector.create("0.3333", min_accuracy=None).to_fraction() == fractions.Fraction(3333, 10000)
assert FracVector.create(["0.33342(10)"]) == FracVector.create(["1/3"])
```

The **binary-rational caveat**: a Python `float` literal is *already* a binary rational, so
`8.04` is not `804/100`. `FracVector.create([8.04])` therefore stores `fractions.Fraction(8.04)`
(a value with a huge denominator), *not* `804/100`. Use the string form `"8.04"` (or an explicit
`Decimal`) when you mean the decimal value:

```python
import fractions
from httk.core import FracVector

assert FracVector.create([8.04]).to_fractions() == [fractions.Fraction(8.04)]
assert FracVector.create([8.04]) != FracVector.create(["8.04"])
```

### The laziness / simplify contract

Most operations deliberately return an **un-simplified** result — they do not reduce to the
smallest denominator. This keeps intermediate arithmetic cheap while staying exact. Call
`.simplify()` at the end of a computation when you want the reduced form:

```python
from httk.core import FracVector

third = FracVector.create("1/3")
product = third * 3            # value is 1, but stored un-simplified
assert product.simplify() == 1
assert product.simplify().denom == 1

messy = FracVector(((2, 4), (6, 8)), 4)
assert messy.simplify().to_tuple() == (2, ((1, 2), (3, 4)))
```

`.simplify()` is idempotent and value-preserving.

### Denominator control

Besides `simplify`, three methods control the denominator explicitly:

- `create(..., denom=D)` divides every nominator by an extra common factor `D`.
- `set_denominator(D)` re-expresses each element as the closest fraction over the fixed
  denominator `D` (reduced resolution).
- `limit_denominator(max_denom)` replaces each element with the closest fraction whose
  denominator is at most `max_denom` — the exact-rational analogue of
  `fractions.Fraction.limit_denominator`, and the tool that recovers a small rational from a
  value that has passed through float.

```python
import fractions
from httk.core import FracVector

assert FracVector.create([[1, 2, 3]], 6).to_tuple() == (6, ((1, 2, 3),))
assert FracVector.create([["1/3", "2/7"]]).set_denominator(1000).to_tuple() == (1000, ((333, 286),))

binary = fractions.Fraction(6004799503160661, 18014398509481984)  # float64 of 1/3
assert FracVector.create([[binary]]).limit_denominator(1000) == FracVector.create([["1/3"]])
```

## Linear algebra tour

`*` is **matrix multiplication**; `+`/`-`/`/` are element-wise; `A ** -1` is the matrix inverse
(`A.inv()`) and `A ** n` is the repeated matrix product (including negative `n`). Every result is
exact:

```python
from httk.core import FracVector

a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])

# determinant (3x3 and 4x4), transpose, inverse:
assert a.det() == -3
assert FracVector.create([[1, 2, 3], [4, 5, 6]]).T() == FracVector.create([[1, 4], [2, 5], [3, 6]])
assert a.inv().simplify().to_tuple() == (3, ((-11, -9, 13), (5, 6, -7), (2, 0, -1)))
assert (a * a.inv()).simplify() == FracVector.eye((3, 3))
assert (a ** -2).simplify() == (a.inv() * a.inv()).simplify()
```

Vector products and the metric:

```python
from httk.core import FracVector

u = FracVector.create([1, 2, 3])
v = FracVector.create([4, 5, 6])

assert u.dot(v) == 32                                   # A . B  (== A * B.T())
assert u.cross(v) == FracVector.create([-3, 6, -3])     # A x B
assert FracVector.create([3, 4, 12]).lengthsqr() == 169 # A * A.T()

# reciprocal cell (rows are reciprocal vectors) and the metric product vecA * M * vecB.T():
metric = FracVector.create([[2, 0, 0], [0, 3, 0], [0, 0, 4]])
ones = FracVector.create([1, 1, 1])
assert metric.metric_product(ones, ones) == 9
```

Other staples: `normalize()` (shift each element into `[0, 1)`), `normalize_half()` (into
`[-1/2, 1/2)`, useful for the shortest vector under periodic boundary conditions), `floor`/`ceil`/
`sign` on scalars, and `max`/`min`/`argmax`/`argmin`/`nargmax`/`nargmin`.

## `MutableFracVector`

`MutableFracVector` is a list-backed variant of `FracVector`. Reach for it when you need to build
or edit a tensor in place — element and slice **assignment** and the `set_*` mutators — rather
than threading copies through a computation. Its inherited (non-`set_`) methods still return
copies, exactly like `FracVector`.

```python
import fractions
from httk.core import FracVector, MutableFracVector

m = MutableFracVector.from_FracVector(FracVector.create([[1, 2, 3], [4, 5, 6]]))
m[1, 1:] = [40, 50]                       # slice assignment
assert m.noms == [[1, 2, 3], [4, 40, 50]]

# assignment puts both sides on a common denominator automatically:
half = MutableFracVector.from_FracVector(FracVector.create([["1/2", "1/2"]]))
half[0, 1] = fractions.Fraction(1, 3)
assert half.to_FracVector().simplify() == FracVector.create([["1/2", "1/3"]])
```

The `set_*` mutators replace the vector in place. `set_inv()` leaves the vector numerically equal
to `FracVector.inv()`, `set_simplify()` reduces to the smallest (integer) denominator, and there
are `set_T`, `set_negative`, `set_normalize`, `set_normalize_half`, `set_set_denominator` too:

```python
from httk.core import FracVector, MutableFracVector

a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
m = MutableFracVector.from_FracVector(a)
m.set_inv()
assert m.to_FracVector() == a.inv()
assert m.denom == 3 and isinstance(m.denom, int)
```

Convert freely between the two: `MutableFracVector.from_FracVector(fv)` and `m.to_FracVector()`
(which returns a plain immutable `FracVector`). `FracVector.use(x)` normalizes any input to an
immutable `FracVector`, converting a `MutableFracVector` through its `to_FracVector()`:

```python
from httk.core import FracVector, MutableFracVector

m = MutableFracVector.from_FracVector(FracVector.create([[1, 2], [3, 4]]))
fv = FracVector.use(m)
assert type(fv) is FracVector
assert fv == m                          # mutable and immutable compare equal by value
```

`FracScalar` is the scalar specialization (a single `nom/denom`), used to make it explicit when a
scalar fracvector is expected.

## `exactmath` and `vectormath`

See {doc}`exactmath` for the full standalone guide to the exact math functions.

The exact transcendental helpers live in `httk.core.vectors.exactmath`: type-preserving
`sqrt`/`cos`/`sin`/`exp`/`pi`/`log`/... . For `fractions.Fraction` input they return exact
rationals computed to a target precision `prec` (given as a `Fraction`) that approximate the true
(generally irrational) value to within `prec`; perfect cases come back exactly. For
`decimal.Decimal` input (or when `digits=` is passed) they instead return a correctly-rounded
`Decimal`.

```python
import decimal
import fractions
import math
from httk.core.vectors import exactmath

F = fractions.Fraction

assert exactmath.sqrt(F(9, 4)) == F(3, 2)                      # perfect square: exact
approx = exactmath.sqrt(F(2), prec=F(1, 10**8))               # irrational: rational approx
assert abs(float(approx) - math.sqrt(2)) < 1e-8

pi = exactmath.pi(prec=F(1, 10**10))
assert abs(float(pi) - math.pi) < 1e-9

# Decimal domain: correctly-rounded to a number of significant digits.
assert exactmath.sqrt(decimal.Decimal(2), digits=12) == decimal.Decimal("1.41421356237")
```

`httk.core.vectors.vectormath` provides `math`-style functional wrappers that dispatch to a
FracVector's own (exact, element-wise) method when given one and fall back to `math` on plain
scalars:

```python
from httk.core import FracVector
from httk.core.vectors import vectormath

# element-wise on a FracVector (exact):
assert vectormath.sqrt(FracVector.create([4, 9])).simplify() == FracVector.create([2, 3])
# plain scalar falls back to math:
assert vectormath.floor(2.7) == 2
```

## Representations and views

Vectors get the same backend/view treatment as the rest of *httk₂*. A **backend** wraps one
concrete representation; a **view** presents any backend through a chosen interface. Functions
accept the `VectorLike` union and normalize immediately to the view they want.

| kind       | backend         | view                | the view *is a* ...            |
| ---------- | --------------- | ------------------- | ------------------------------ |
| `"frac"`   | `VectorFrac`    | `VectorFracView`    | `FracVector` (exact algebra)   |
| `"native"` | `VectorNative`  | `VectorNativeView`  | nested `tuple` (exact leaves)  |
| `"numpy"`  | `VectorNumpy`   | `VectorNumpyView`   | `numpy.ndarray` (float64)      |

```python
from httk.core import FracVector, VectorFracView, VectorNativeView
from httk.core.vectors import VectorBackend, VectorFrac, VectorNative

# Dispatch by input type:
assert isinstance(VectorBackend.create([[1, 2], [3, 4]]), VectorNative)
assert isinstance(VectorBackend.create(FracVector.create([[1, 2], [3, 4]])), VectorFrac)

# A frac view is a genuine FracVector, so the full exact algebra is available:
assert VectorFracView([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).det() == -3

# A native view is a genuine nested tuple. By default it presents natively-held leaves verbatim
# (see "Element types" below); a leaf codec, e.g. leaf="fraction", converts them:
import fractions
assert VectorNativeView([["1/3", "2/3"]]) == (("1/3", "2/3"),)
assert VectorNativeView([["1/3", "2/3"]], leaf="fraction") == ((fractions.Fraction(1, 3), fractions.Fraction(2, 3)),)
```

The canonical interchange between representations is **exactness-preserving**: every backend
exposes `.fractions` (a nested tuple of `fractions.Fraction`, or a bare `Fraction` for a scalar)
and `.dim`. Because numpy float64 values are themselves binary rationals, even a numpy array
produces `.fractions` *exactly*.

### Element types (leaves)

The backends above choose the **container** (a `FracVector`, a nested `tuple`, a `numpy.ndarray`).
A *leaf codec* chooses the orthogonal **element domain** — what a single leaf value is presented as
(an `int`, a `fractions.Fraction`, a `float`, a `decimal.Decimal`, ...). The two axes are
independent: any container can carry any leaf type. Leaf codecs live in
`httk.core.vectors.leaf_codecs` and are an extensible registry, exactly like the compression codecs.

The key policy is that **a view never raises on the data**. A backend always keeps the exact
original, so any lossy view is fully recoverable simply by re-viewing; therefore a leaf codec that
cannot represent a value exactly still produces a view, applying its *documented default
conversion*. Only configuration errors — an unknown codec name or an invalid option — raise, and
they raise eagerly at view construction.

#### The preserve-original default

The default native view of natively-held data now presents its leaves **verbatim** — the identical
objects, with only the list/tuple containers tuple-ized. `Decimal`s in, the same `Decimal`s out; no
silent Fraction-ization:

```python
import decimal
from httk.core import VectorNativeView

d = decimal.Decimal("1.5")
nv = VectorNativeView([[d, 2], [3, 4]])
assert nv == ((decimal.Decimal("1.5"), 2), (3, 4))
assert nv[0][0] is d                    # the very same Decimal object
assert [type(x) for x in nv[0]] == [decimal.Decimal, int]
```

Because the leaves are untouched, string leaves stay strings under the default — ask for a codec
when you want them converted (see below). When the source instead *crosses* representations (a
`frac` or `numpy` backend, which holds no native leaves to preserve), the default is the `"exact"`
codec — `int` when integral, otherwise `Fraction`, never a float, exactly as before:

```python
import fractions
from httk.core import FracVector, VectorNativeView

crossed = VectorNativeView(FracVector.create([["1/3", "2/3"], [1, 2]]))
assert crossed == ((fractions.Fraction(1, 3), fractions.Fraction(2, 3)), (1, 2))
```

#### Choosing a leaf codec

Pass `leaf=` (plus any codec options) to convert every element from the backend's exact `fractions`
hub. The built-ins:

| `leaf=`      | leaf type            | exactness contract / default conversion                                   |
| ------------ | -------------------- | ------------------------------------------------------------------------- |
| `"exact"`    | `int` or `Fraction`  | always exact — `int` when integral, else `Fraction`                       |
| `"fraction"` | `Fraction`           | always exact                                                              |
| `"int"`      | `int`                | exact when integral; else `rounding=` (`"round"` half-even default)        |
| `"float"`    | `float`              | inherently lossy: nearest IEEE-754 binary double                          |
| `"decimal"`  | `Decimal`            | exact for `2**a * 5**b` denominators; else `digits=` sig. figs, half-even |

The `"int"` codec's default rounding is nearest with ties to even (matching Python's `round` on a
`Fraction`); `rounding=` also accepts `"floor"`, `"ceil"`, and `"trunc"`:

```python
from httk.core import FracVector, VectorNativeView

halves = FracVector.create([["5/2", "7/2", "-5/2", "-7/2"]])
assert VectorNativeView(halves, leaf="int") == ((2, 4, -2, -4),)                     # half-even
assert VectorNativeView(halves, leaf="int", rounding="floor") == ((2, 3, -3, -4),)
assert VectorNativeView(halves, leaf="int", rounding="ceil") == ((3, 4, -2, -3),)
assert VectorNativeView(halves, leaf="int", rounding="trunc") == ((2, 3, -2, -3),)
```

The `"decimal"` codec is **exact** whenever the reduced denominator is of the form `2**a * 5**b` (a
finite decimal expansion) — regardless of the active `decimal` context precision. Otherwise the
value has no finite decimal expansion, so it is quantized to `digits=` significant digits (default:
the active context precision) with round-half-even:

```python
import decimal
from httk.core import FracVector, VectorNativeView

# 1/8 has a finite expansion: exact.
assert VectorNativeView(FracVector.create([["1/8"]]), leaf="decimal") == ((decimal.Decimal("0.125"),),)
# 1/3 does not: quantized to the requested number of significant digits.
assert VectorNativeView(FracVector.create([["1/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.333333"),),)
```

And `leaf="float"` is the lossy-by-design bridge to plain floats (`leaf="fraction"` converts the
preserved strings from the first example):

```python
import fractions
from httk.core import FracVector, VectorNativeView

assert VectorNativeView(FracVector.create([["1/3"]]), leaf="float") == ((1.0 / 3.0,),)
assert VectorNativeView([["1/3", "2/3"]], leaf="fraction") == ((fractions.Fraction(1, 3), fractions.Fraction(2, 3)),)
```

Only *configuration* errors raise, and eagerly — an unknown codec name or an option a codec does not
accept:

```python
from httk.core import VectorNativeView

for bad in [dict(leaf="nope"), dict(leaf="int", rounding="sideways"), dict(leaf="float", digits=3)]:
    try:
        VectorNativeView([[1, 2]], **bad)
        raise AssertionError("expected a ValueError")
    except ValueError:
        pass
```

#### The invariant

Viewing is non-destructive: after *any* lossy view, `unwrap()` still returns the identical original
object, and a fresh exact view reproduces the exact values.

```python
import decimal
from httk.core import VectorNative, VectorNativeView
from httk.core.views import unwrap

raw = [["1/3", decimal.Decimal("2.5"), 4]]
backend = VectorNative(raw)

lossy = VectorNativeView(backend, leaf="int")     # 1/3 -> 0, 5/2 -> 2 (half-even)
assert lossy == ((0, 2, 4),)
assert unwrap(backend) is raw                      # the original object, untouched
import fractions
assert VectorNativeView(backend, leaf="exact") == ((fractions.Fraction(1, 3), fractions.Fraction(5, 2), 4),)
```

#### Numpy dtypes

The numpy view carries the same idea through `dtype=` (default `float64`). For an **integer** dtype,
each element is rounded through the `"int"` codec's default (nearest, half-even) via the exact
Fraction hub *before* the array is built — so numpy never silently truncates a fractional value:

```python
import numpy
from httk.core import FracVector, VectorNumpyView

exact = VectorNumpyView([[1, 2], [3, 4]], dtype=numpy.int64)
assert exact.dtype == numpy.int64 and exact.tolist() == [[1, 2], [3, 4]]

rounded = VectorNumpyView(FracVector.create([["1/2", "3/2", "5/2", "7/2"]]), dtype=numpy.int64)
assert rounded.tolist() == [[0, 2, 2, 4]]          # half-even, not truncation
```

#### Registering a custom leaf codec

A leaf codec is a `LeafCodec` — a name, a `from_fraction(value, **options)` conversion from the
canonical `Fraction` hub, and an option validator — registered with `register_leaf_codec`. Once
registered it is usable through the `leaf=` hint like any built-in:

```python
import fractions
from httk.core import FracVector, LeafCodec, VectorNativeView, known_leaf_codecs, register_leaf_codec

def _to_percent(value: fractions.Fraction) -> str:
    return f"{float(value * 100):g}%"

def _no_options(options: dict) -> None:
    if options:
        raise ValueError("percent codec takes no options")

register_leaf_codec(LeafCodec("percent", _to_percent, _no_options))
assert "percent" in known_leaf_codecs()
assert VectorNativeView(FracVector.create([["1/4", "1/2"]]), leaf="percent") == (("25%", "50%"),)
```

### The numpy view, exact capture, and lossiness

numpy support is an optional dependency; install it with the extra:

```bash
pip install "httk-core[numpy]"
```

`VectorNumpyView(fracvector)` produces a plain float64 matrix — the fast path into numeric code.
It is the one lossy step (rationals become their nearest binary value), so a 3×3 exact cell
matrix converts to a plain float matrix identically to `FracVector.to_floats()`:

```python
import numpy
from httk.core import FracVector, VectorNumpyView

cell = FracVector.create([["8.04", "0.0", "0.0"],
                          ["0.0", "3.72", "0.0"],
                          ["0.0", "0.0", "7.38"]])

arr = VectorNumpyView(cell)               # a genuine float64 ndarray
assert isinstance(arr, numpy.ndarray)
assert arr.dtype == numpy.float64 and arr.shape == (3, 3)
assert arr.tolist() == cell.to_floats()   # same float matrix as to_floats()
```

Going the other way, `VectorFracView(ndarray)` captures a float64 array's values as **exact**
binary rationals. A value that has genuinely passed through a raw float64 array therefore does not
return as its original decimal fraction — but `limit_denominator` recovers the intended small
rational:

```python
import numpy
from httk.core import FracVector, VectorNumpyView, VectorFracView

one_third = FracVector.create([["1/3"]])
detached = numpy.asarray(VectorNumpyView(one_third))   # a detached plain float64 array
back = VectorFracView(detached)                        # captures the binary rational exactly

assert back.simplify() != one_third                    # it is the float64 value of 1/3
assert back.limit_denominator(100).simplify() == one_third
```

(This mirrors the orientation-lossiness note for cell parameters in *httk-atomistic*.)

When numpy is not installed, the numpy backend and view are simply not registered (the numpy view
module subclasses `numpy.ndarray`, so it cannot even be imported without numpy). Everything else —
the exact library and the frac/native family — works unchanged, and dispatch just never selects a
numpy backend.

### `unwrap`

`unwrap(obj)` returns the most raw representation available: the wrapped `FracVector` for a frac
backend, the original nested sequence for a native backend, and the underlying `ndarray` for a
numpy backend. For anything that is not a view/backend it returns the object unchanged.
