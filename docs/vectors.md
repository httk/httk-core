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

## `fracmath` and `vectormath`

The exact transcendental helpers live in `httk.core.vectors.fracmath`: rational approximations of
`sqrt`/`cos`/`sin`/`exp`/`pi`/`log`/... on `fractions.Fraction`, each computed to a target
precision `prec` (given as a `Fraction`). Results are exact rationals that approximate the true
(generally irrational) value to within `prec`; perfect cases come back exactly.

```python
import fractions
import math
from httk.core.vectors import fracmath

F = fractions.Fraction

assert fracmath.frac_sqrt(F(9, 4)) == F(3, 2)                      # perfect square: exact
approx = fracmath.frac_sqrt(F(2), prec=F(1, 10**8))               # irrational: rational approx
assert abs(float(approx) - math.sqrt(2)) < 1e-8

pi = fracmath.frac_pi(prec=F(1, 10**10))
assert abs(float(pi) - math.pi) < 1e-9
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

# A native view is a genuine nested tuple with exact leaves (int when integral, else Fraction):
import fractions
assert VectorNativeView([["1/3", "2/3"]]) == ((fractions.Fraction(1, 3), fractions.Fraction(2, 3)),)
```

The canonical interchange between representations is **exactness-preserving**: every backend
exposes `.fractions` (a nested tuple of `fractions.Fraction`, or a bare `Fraction` for a scalar)
and `.dim`. Because numpy float64 values are themselves binary rationals, even a numpy array
produces `.fractions` *exactly*.

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
