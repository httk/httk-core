# Vectors in detail

This page documents numerical vectors and the exact-rational vector library in
`httk.core.vectors`, including the backend/view family that lets the same tensor data be viewed as
plain nested sequences, numpy arrays, or exact values.

## Numerical vectors first

The fastest way to operate on numerical vectors in *httk₂* is to choose the presentation you need:
plain native leaves with `VectorNativeView`, numpy with `VectorNumpyView` or `to_numeric`, and
`Decimal` values through the leaf codecs. Plain floats and numpy arrays are convenient but lossy;
they round exact fractions to binary floating-point values. Native views preserve native leaves by
default, while an explicit codec makes the conversion choice visible.

```python
from decimal import Decimal

import numpy

from httk.core.vectors import (
    FracVector,
    NumericVector,
    VectorNativeView,
    VectorNumpyView,
    to_numeric,
)

values = [["1/3", 2], ["3/4", 4]]
native = VectorNativeView(values)                  # nested tuples, native leaves preserved
floats = VectorNativeView(values, leaf="float")   # nested tuples of plain floats
array = VectorNumpyView(values)                    # float64 ndarray
numeric: NumericVector = to_numeric(values)       # ndarray for a tensor, float for a scalar
decimals = VectorNativeView(FracVector(values), leaf="decimal", digits=6)

assert native == (("1/3", 2), ("3/4", 4))
assert floats[0][0] == 1 / 3 and isinstance(array, numpy.ndarray)
assert decimals[0][0] == Decimal("0.333333")
```

The float and numpy presentations are intentionally lossy: `1/3` becomes the nearest binary
float. The exact backend remains available for re-viewing, while `VectorNativeView(...,
leaf="decimal", digits=...)` gives controlled decimal output.

*httk₂* can also work exact-first. Use that route when the values themselves, rather than only
their numerical presentation, must survive arithmetic unchanged.

## Exact rational arithmetic

`FracVector` is an immutable N-dimensional tensor stored as a nested tuple of integer nominators
over a single shared integer denominator. All arithmetic is exact — there is no floating-point
rounding anywhere — which makes it well suited to crystallography, where cell vectors and reduced
coordinates are naturally rational.

```python
from httk.core.vectors import FracVector

cell = FracVector([["8.04", "0.0", "0.0"],
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
from httk.core.vectors import FracVector

assert FracVector.from_noms_and_denom(((1,),), 2) == FracVector.from_noms_and_denom(((2,),), 4)   # both are 1/2
```

### Creation from every numeric type

`FracVector(...)` accepts nested lists/tuples whose leaves are any of the following:

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
from httk.core.vectors import FracVector

# int, str, Decimal and Fraction leaves all land on their exact rational value:
assert FracVector([decimal.Decimal("0.25"), decimal.Decimal("2.125")]).to_tuple() == (8, (2, 17))
assert FracVector([fractions.Fraction(2, 3), fractions.Fraction(3, 4)]).to_tuple() == (12, (8, 9))
assert FracVector("2/3").to_fraction() == fractions.Fraction(2, 3)
```

String input is parsed for significant digits, so a written decimal is taken at its stated
precision (and an explicit standard deviation is honored) rather than as an exact binary float:

```python
import fractions
from httk.core.vectors import FracVector

FracVector("0.33")                      # -> 33/100  (0.33 assumed to mean 0.3300)
FracVector("0.3333")                    # -> 1/3     (enough digits to imply 1/3)
FracVector("0.33", min_accuracy=None)   # -> 33/100, converted exactly
FracVector(["0.33342(10)"])             # -> 1/3, using the explicit standard deviation

assert FracVector("0.33").to_fraction() == fractions.Fraction(33, 100)
assert FracVector("0.3333").to_fraction() == fractions.Fraction(1, 3)
assert FracVector("0.3333", min_accuracy=None).to_fraction() == fractions.Fraction(3333, 10000)
assert FracVector(["0.33342(10)"]) == FracVector(["1/3"])
```

The **binary-rational caveat**: a Python `float` literal is *already* a binary rational, so
`8.04` is not `804/100`. `FracVector([8.04])` therefore stores `fractions.Fraction(8.04)`
(a value with a huge denominator), *not* `804/100`. Use the string form `"8.04"` (or an explicit
`Decimal`) when you mean the decimal value:

```python
import fractions
from httk.core.vectors import FracVector

assert FracVector([8.04]).to_fractions() == [fractions.Fraction(8.04)]
assert FracVector([8.04]) != FracVector(["8.04"])
```

### The laziness / simplify contract

Most operations return an **un-simplified** result — they do not reduce to the
smallest denominator. This keeps intermediate arithmetic cheap while staying exact. Call
`.simplify()` at the end of a computation when you want the reduced form:

```python
from httk.core.vectors import FracVector

third = FracVector("1/3")
product = third * 3            # value is 1, but stored un-simplified
assert product.simplify() == 1
assert product.simplify().denom == 1

messy = FracVector.from_noms_and_denom(((2, 4), (6, 8)), 4)
assert messy.simplify().to_tuple() == (2, ((1, 2), (3, 4)))
```

`.simplify()` is idempotent and value-preserving.

### Denominator control

Besides `simplify`, three methods control the denominator explicitly:

- `FracVector(..., denom=D)` divides every nominator by an extra common factor `D`.
- `set_denominator(D)` re-expresses each element as the closest fraction over the fixed
  denominator `D` (reduced resolution).
- `limit_denominator(max_denom)` replaces each element with the closest fraction whose
  denominator is at most `max_denom` — the exact-rational analogue of
  `fractions.Fraction.limit_denominator`, and the tool that recovers a small rational from a
  value that has passed through float.

```python
import fractions
from httk.core.vectors import FracVector

assert FracVector([[1, 2, 3]], denom=6).to_tuple() == (6, ((1, 2, 3),))
assert FracVector([["1/3", "2/7"]]).set_denominator(1000).to_tuple() == (1000, ((333, 286),))

binary = fractions.Fraction(6004799503160661, 18014398509481984)  # float64 of 1/3
assert FracVector([[binary]]).limit_denominator(1000) == FracVector([["1/3"]])
```

## Linear algebra tour

`*` is **matrix multiplication**; `+`/`-`/`/` are element-wise; `A ** -1` is the matrix inverse
(`A.inv()`) and `A ** n` is the repeated matrix product (including negative `n`). Every result is
exact:

```python
from httk.core.vectors import FracVector

a = FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]])

# determinant (3x3 and 4x4), transpose, inverse:
assert a.det() == -3
assert FracVector([[1, 2, 3], [4, 5, 6]]).T() == FracVector([[1, 4], [2, 5], [3, 6]])
assert a.inv().simplify().to_tuple() == (3, ((-11, -9, 13), (5, 6, -7), (2, 0, -1)))
assert (a * a.inv()).simplify() == FracVector.eye((3, 3))
assert (a ** -2).simplify() == (a.inv() * a.inv()).simplify()
```

Vector products and the metric:

```python
from httk.core.vectors import FracVector

u = FracVector([1, 2, 3])
v = FracVector([4, 5, 6])

assert u.dot(v) == 32                                   # A . B  (== A * B.T())
assert u.cross(v) == FracVector([-3, 6, -3])     # A x B
assert FracVector([3, 4, 12]).lengthsqr() == 169 # A * A.T()

# reciprocal cell (rows are reciprocal vectors) and the metric product vecA * M * vecB.T():
metric = FracVector([[2, 0, 0], [0, 3, 0], [0, 0, 4]])
ones = FracVector([1, 1, 1])
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
from httk.core.vectors import FracVector, MutableFracVector

m = MutableFracVector(FracVector([[1, 2, 3], [4, 5, 6]]))
m[1, 1:] = [40, 50]                       # slice assignment
assert m.noms == [[1, 2, 3], [4, 40, 50]]

# assignment puts both sides on a common denominator automatically:
half = MutableFracVector(FracVector([["1/2", "1/2"]]))
half[0, 1] = fractions.Fraction(1, 3)
assert FracVector(half).simplify() == FracVector([["1/2", "1/3"]])
```

The `set_*` mutators replace the vector in place. `set_inv()` leaves the vector numerically equal
to `FracVector.inv()`, `set_simplify()` reduces to the smallest (integer) denominator, and there
are `set_T`, `set_negative`, `set_normalize`, `set_normalize_half`, `set_set_denominator` too:

```python
from httk.core.vectors import FracVector, MutableFracVector

a = FracVector([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
m = MutableFracVector(a)
m.set_inv()
assert FracVector(m) == a.inv()
assert m.denom == 3 and isinstance(m.denom, int)
```

Convert freely between the two: `MutableFracVector(fv)` and `FracVector(m)`
(which returns a plain immutable `FracVector`). `FracVector(x)` normalizes any input to an
immutable `FracVector`:

```python
from httk.core.vectors import FracVector, MutableFracVector

m = MutableFracVector(FracVector([[1, 2], [3, 4]]))
fv = FracVector(m)
assert type(fv) is FracVector
assert fv == m                          # mutable and immutable compare equal by value
```

`FracScalar` is the scalar specialization (a single `nom/denom`), used to make it explicit when a
scalar fracvector is expected.

## `exactmath` and `vectormath`

See {doc}`exactmath` for the full standalone guide to the exact math functions.

The exact transcendental helpers live in `httk.core.exactmath`: type-preserving
`sqrt`/`cos`/`sin`/`exp`/`pi`/`log`/... . For `fractions.Fraction` input they return exact
rationals computed to a target precision `prec` (given as a `Fraction`) that approximate the true
(generally irrational) value to within `prec`; perfect cases come back exactly. For
`decimal.Decimal` input (or when `digits=` is passed) they instead return a correctly-rounded
`Decimal`.

```python
import decimal
import fractions
import math
from httk.core import exactmath

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
from httk.core.vectors import FracVector
from httk.core.vectors import vectormath

# element-wise on a FracVector (exact):
assert vectormath.sqrt(FracVector([4, 9])).simplify() == FracVector([2, 3])
# plain scalar falls back to math:
assert vectormath.floor(2.7) == 2
```

## Exact radicals: `SurdVector`

Symmetry lives in **fractional** coordinates, and there it needs no radicals: point-group
operations are integer matrices and translations are rational, so `FracVector` closes the whole
algebra exactly. Radicals appear only when you move to a **Cartesian** frame — the hexagonal basis
carries a $\sqrt3$, Cartesian rotations carry $\sqrt2$/$\sqrt3$, and a bond length is
$\sqrt{\text{rational}}$ under a rational metric. `SurdVector` is the exact-arithmetic model for
that Cartesian layer: it closes the rationals *and* the square roots of arbitrary positive
rationals under `+`, `-`, `*`, `/`. Its values form the field
$\mathbb{Q}[\sqrt n : n\ \text{squarefree}]$ — finite sums $\sum_r q_r\sqrt r$ with rational
coefficients — stored canonically as a `{squarefree radicand → rational coefficient}` map (unique,
because the $\sqrt r$ are linearly independent over $\mathbb{Q}$), so equality and zero-detection
are exact.

```{admonition} Purpose boundary — magnitudes vs. linear structure
:class: important

For pure **magnitude** questions — comparing, sorting, or equating distances — stay with the
*squared* representation: a squared length `lengthsqr` is rational and a Gram/metric matrix
`G = B*B.T()` is rational, so "is bond A shorter than bond B?" is an exact rational comparison,
already fully supported by `FracVector`, and it is the cheaper recommended fast path.

Reach for `SurdVector` only when radicals sit inside **additive / linear** structure, where
squaring fails: components are signed and additive so $(a+b)^2\neq a^2+b^2$ (the cross term is
itself a radical); a metric fixes a basis only up to an orthogonal transformation, so squaring
discards orientation and chirality; and even scalar sums are not closed, $(\sqrt2+\sqrt3)^2 =
5+2\sqrt6$. `SurdVector` composes *with* the squared strategy rather than replacing it: whenever a
value lands back in the rationals its canonical form collapses to the plain rational again.
```

### Square roots, products, and the nested-radical limit

`SurdVector.sqrt_of(q)` takes the exact square root of any nonnegative rational — a plain rational
when `q` is a perfect square, otherwise a canonical single-radical surd. Products combine radicands
($\sqrt r\,\sqrt s = c\,\sqrt t$), and a value that squares back to a rational *is* rational again:

```python
import fractions
from httk.core.vectors import SurdVector

F = fractions.Fraction

assert SurdVector.sqrt_of(8) == SurdVector.from_radicand_map({2: 2})       # 2*sqrt(2)
assert SurdVector.sqrt_of(F(4, 9)) == SurdVector(F(2, 3))           # perfect square: rational
assert SurdVector.sqrt_of(F(1, 2)) == SurdVector.sqrt_of(2) * SurdVector(F(1, 2))  # sqrt(2)/2
assert SurdVector.sqrt_of(2) * SurdVector.sqrt_of(3) == SurdVector.sqrt_of(6)
assert SurdVector.sqrt_of(2) * SurdVector.sqrt_of(2) == SurdVector(2)
assert str(SurdVector.sqrt_of(3) * SurdVector(F(1, 2))) == "(1/2)*sqrt(3)"
```

The field is closed under `+`, `-`, `*`, and full `/` (division rationalizes the denominator by
iterated conjugation), but **not** under `sqrt` of a surd — there are no nested radicals. So
`length()` is exact precisely when `lengthsqr()` is rational, and it raises otherwise:

```python
from httk.core.vectors import SurdVector

# 1/(1 + sqrt2 + sqrt3) is a genuine field inverse (verify by multiplying back):
d = SurdVector.one() + SurdVector.sqrt_of(2) + SurdVector.sqrt_of(3)
assert (SurdVector.one() / d) * d == SurdVector.one()
```

### Exact comparison

Ordering and sign are decided **exactly**, by refining rational bounds on each $\sqrt r$ until the
sign resolves (a nonzero surd is never zero, so this always terminates):

```python
from httk.core.vectors import SurdVector

lhs = SurdVector.sqrt_of(2) + SurdVector.sqrt_of(3)   # ~3.1463
rhs = SurdVector.sqrt_of(10)                          # ~3.1623
assert lhs < rhs
```

### A hexagonal Cartesian basis

The standard hexagonal basis $B = \begin{bmatrix} a & 0 & 0\\ -a/2 & a\sqrt3/2 & 0\\ 0 & 0 & c\end{bmatrix}$
has rational `a`, `c` but an irrational entry $a\sqrt3/2$. Its determinant, inverse, and the metric
$G = B\,B^\mathsf{T}$ are all exact, and a Cartesian bond length comes back as an exact radical:

```python
import fractions
from httk.core.vectors import FracVector, SurdVector

F = fractions.Fraction
a, c = F(3), F(5)

# Assemble B from its rational part (radicand 1) and its sqrt(3) part (radicand 3):
B = SurdVector.from_radicand_map({
    1: [[a, 0, 0], [-a / 2, 0, 0], [0, 0, c]],
    3: [[0, 0, 0], [0, a / 2, 0], [0, 0, 0]],
})

identity = SurdVector(FracVector.eye((3, 3)))
assert B.det() == SurdVector.from_radicand_map({3: F(45, 2)})   # (45/2)*sqrt(3)
assert B * B.inv() == identity                                  # exact inverse
assert (B * B.T()).is_rational                                  # the metric is rational

# The second basis row is a Cartesian vector of exact length a:
row1 = SurdVector.from_radicand_map({1: [-a / 2, 0, 0], 3: [0, a / 2, 0]})
assert row1.lengthsqr() == SurdVector(a * a)
assert row1.length() == SurdVector(a)

# A vector whose squared length is irrational (3 + 2*sqrt(2)) has a nested-radical length:
v = SurdVector.from_radicand_map({1: [1, 0, 0], 2: [1, 0, 0]})
assert not v.lengthsqr().is_rational
try:
    v.length()
    raise AssertionError("expected a ValueError")
except ValueError:
    pass
```

### Decimal rendering

A `SurdScalar` renders as a correctly-rounded `Decimal`, reusing the same `exactmath` Ziv machinery
as {doc}`exactmath`: a rational surd renders its exact finite expansion, an irrational one is
correctly rounded to the requested significant digits, and repeated calls are identical:

```python
import decimal
from httk.core.vectors import SurdVector

assert SurdVector.sqrt_of(2).to_decimal(digits=30) == decimal.Decimal("1.41421356237309504880168872421")
assert SurdVector.sqrt_of(8).to_decimal(digits=6) == decimal.Decimal("2.82843")
assert SurdVector.sqrt_of(9).to_decimal(digits=30) == decimal.Decimal("3")   # rational: exact
```

### Exact degree trigonometry (Niven's theorem)

Crystallographic cell angles are given in whole degrees, and for the common ones the cosine is an
exact surd. `SurdScalar.cos_degrees` / `sin_degrees` return that exact value whenever the angle —
reduced modulo 360 — is a **multiple of 15 or of 36 degrees**, and `None` otherwise. That list is
complete: $\cos(2\pi a/b)$ lies in a field generated by square roots of rationals iff the Galois
group $(\mathbb{Z}/b)^\times/\{\pm1\}$ of $\mathbb{Q}(\cos 2\pi/b)$ has exponent at most 2, which
holds exactly for $b \in \{1,2,3,4,5,6,8,10,12,24\}$ — i.e. the multiples of 15° (like
$\cos 15° = \tfrac{\sqrt6+\sqrt2}{4}$) and of 36° (the golden-ratio family,
$\cos 36° = \tfrac{1+\sqrt5}{4}$). **Niven's theorem** is the rational-value special case of this
classification, so a `None` result is a *proof* that the exact value is outside the field — the
caller then falls back to `exactmath.cos(..., degrees=True)` for a deterministic rational
approximation. `SurdScalar.acos_degrees` is the exact reverse lookup, returning the angle in
degrees over $[0, 180]$ when the value is one of the table cosines:

```python
import fractions
from httk.core.vectors import SurdVector, SurdScalar

F = fractions.Fraction

# Exact for multiples of 15 / 36 degrees; angle reduced mod 360; int / Fraction / str accepted:
assert SurdScalar.cos_degrees(30) == SurdVector.sqrt_of(3) / 2      # (1/2)*sqrt(3)
assert SurdScalar.sin_degrees(60) == SurdVector.sqrt_of(3) / 2
assert SurdScalar.cos_degrees(15) == (SurdVector.sqrt_of(6) + SurdVector.sqrt_of(2)) / 4
assert SurdScalar.cos_degrees(36) == (SurdVector.one() + SurdVector.sqrt_of(5)) / 4
assert SurdScalar.cos_degrees(120) == SurdVector(F(-1, 2))
assert SurdScalar.cos_degrees("390") == SurdScalar.cos_degrees(30)  # reduced mod 360

# sin^2 + cos^2 == 1 holds EXACTLY in the field:
c, s = SurdScalar.cos_degrees(30), SurdScalar.sin_degrees(30)
assert c * c + s * s == SurdVector.one()

# The 36-degree family is exact for cos only: sin(36) = cos(54) is NOT a surd (54 is a multiple
# of neither 15 nor 36), while the 15-degree family is exact for both:
assert SurdScalar.sin_degrees(36) is None
assert SurdScalar.sin_degrees(15) == SurdScalar.cos_degrees(75)

# A non-special angle has a cosine outside the field -> None (a proof of inexactness):
assert SurdScalar.cos_degrees(20) is None

# Exact reverse lookup over [0, 180]; a non-table value reverses to None:
assert (SurdVector.sqrt_of(3) / 2)._as_scalar().acos_degrees() == F(30)
assert ((SurdVector.one() + SurdVector.sqrt_of(5)) / 4)._as_scalar().acos_degrees() == F(36)
assert SurdVector(F(1, 3))._as_scalar().acos_degrees() is None
```

## Representations and views

Vectors get the same backend/view treatment as the rest of *httk₂*. A **backend** wraps one
concrete representation; a **view** presents any backend through a chosen interface. Functions
accept the `VectorLike` union and normalize immediately to the view they want.

| kind       | backend         | view                | the view *is a* ...            |
| ---------- | --------------- | ------------------- | ------------------------------ |
| `"frac"`   | `FracVector`           | `VectorFracView`    | `FracVector` (exact algebra)   |
| `"surd"`   | `SurdVector`           | `VectorSurdView`    | `SurdVector` (exact radicals)  |
| `"native"` | `VectorNativeBackend`  | `VectorNativeView`  | nested `tuple` (exact leaves)  |
| `"numpy"`  | `VectorNumpyBackend`   | `VectorNumpyView`   | `numpy.ndarray` (float64)      |

`VectorFracView` and `VectorSurdView` are lazy: construction stores the backend, and their exact
presentation state is converted and kept on first access. The other views remain eager where their
representation or documented construction-time validation requires it.

`FracVector` and `SurdVector` are also their own backends: dispatch adopts each immutable value by
identity, with no wrapper or copy. `MutableFracVector` is a sibling through the internal
`FracVectorBase` and is never adopted; freeze it first with `FracVector(mutable)`.

```python
from httk.core.vectors import FracVector, VectorFracView, VectorNativeView
from httk.core.vectors import VectorBackend, VectorNativeBackend

# Dispatch by input type:
assert isinstance(VectorBackend.create([[1, 2], [3, 4]]), VectorNativeBackend)
frac = FracVector([[1, 2], [3, 4]])
assert VectorBackend.create(frac) is frac

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

On top of the hub, the `VectorAPI` contract guarantees the float renderings `to_floats()`
(nested plain-`float` **lists**, matching the `numpy.ndarray.tolist()` convention and directly
JSON-serializable; a bare `float` for a scalar) and `to_float()` (scalars only) on every backend —
and the exact value types `FracVector` and `SurdVector` honor the same contract with their own
implementations, with `float(...)` additionally working on every exact scalar (`FracVector`,
`SurdScalar`). So *whatever* object the family hands you, `.to_floats()` works — domain libraries
built on the family (e.g. *httk₂*'s atomistic structures) therefore return exact vector objects
from their accessors and add no ad-hoc float-conversion methods of their own:

```python
import fractions
from httk.core.vectors import FracVector, SurdVector
from httk.core.vectors import VectorBackend

assert FracVector([["1/2", "1/4"]]).to_floats() == [[0.5, 0.25]]
assert VectorBackend.create([[1, 2], [3, 4]]).to_floats() == [[1.0, 2.0], [3.0, 4.0]]
assert float(SurdVector.sqrt_of(4)) == 2.0                       # exact scalars support float()
assert SurdVector.sqrt_of(2).to_float() == float(SurdVector.sqrt_of(2))
```

The `surd` backend is the one representation whose values are not all rational, so it sits at the
edges of that exactness table asymmetrically. A **rational → surd** conversion is exact (every
rational is the radicand-1 term of a surd), and a `VectorSurdView` of a frac/native/numpy backend
therefore round-trips exactly:

```python
import fractions
from httk.core.vectors import SurdVector, VectorSurdView
from httk.core.vectors import VectorBackend
from httk.core.views import unwrap

# Dispatch by input type; SurdVector is its own backend and is adopted by identity:
surd = SurdVector.sqrt_of(2)
assert VectorBackend.create(surd) is surd

# rational -> surd view is exact:
view = VectorSurdView([["1/3", "2/5"]])
assert view == SurdVector([["1/3", "2/5"]]) and view.is_rational

# unwrap returns the exact original SurdVector, radicals intact:
assert unwrap(surd) is surd
```

Going the other way, a genuinely **irrational surd → rational** representation (its `.fractions`
hub, or any frac/native/numpy view) is **lossy but deterministic**: the value is reduced to a
reproducible rational approximation at the active decimal-context precision plus a small guard, and
the exact original is always recoverable from the backend via `unwrap`. Its lossiness row therefore
reads: rational → surd exact; surd → rational lossy-deterministic (exact original recoverable).

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

The default native view of natively-held data presents its leaves **verbatim** — the identical
objects, with only the list/tuple containers tuple-ized. `Decimal`s in, the same `Decimal`s out; no
silent Fraction-ization:

```python
import decimal
from httk.core.vectors import VectorNativeView

d = decimal.Decimal("1.5")
nv = VectorNativeView([[d, 2], [3, 4]])
assert nv == ((decimal.Decimal("1.5"), 2), (3, 4))
assert nv[0][0] is d                    # the very same Decimal object
assert [type(x) for x in nv[0]] == [decimal.Decimal, int]
```

Because the leaves are untouched, string leaves stay strings under the default — ask for a codec
when you want them converted (see below). When the source instead *crosses* representations (a
`frac` or `numpy` backend, which holds no native leaves to preserve), the default is the `"exact"`
codec — `int` when integral, otherwise `Fraction`, never a float:

```python
import fractions
from httk.core.vectors import FracVector, VectorNativeView

crossed = VectorNativeView(FracVector([["1/3", "2/3"], [1, 2]]))
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
from httk.core.vectors import FracVector, VectorNativeView

halves = FracVector([["5/2", "7/2", "-5/2", "-7/2"]])
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
from httk.core.vectors import FracVector, VectorNativeView

# 1/8 has a finite expansion: exact.
assert VectorNativeView(FracVector([["1/8"]]), leaf="decimal") == ((decimal.Decimal("0.125"),),)
# 1/3 does not: quantized to the requested number of significant digits.
assert VectorNativeView(FracVector([["1/3"]]), leaf="decimal", digits=6) == ((decimal.Decimal("0.333333"),),)
```

And `leaf="float"` is the lossy-by-design bridge to plain floats (`leaf="fraction"` converts the
preserved strings from the first example):

```python
import fractions
from httk.core.vectors import FracVector, VectorNativeView

assert VectorNativeView(FracVector([["1/3"]]), leaf="float") == ((1.0 / 3.0,),)
assert VectorNativeView([["1/3", "2/3"]], leaf="fraction") == ((fractions.Fraction(1, 3), fractions.Fraction(2, 3)),)
```

Only *configuration* errors raise, and eagerly — an unknown codec name or an option a codec does not
accept:

```python
from httk.core.vectors import VectorNativeView

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
from httk.core.vectors import VectorNativeBackend, VectorNativeView
from httk.core.views import unwrap

raw = [["1/3", decimal.Decimal("2.5"), 4]]
backend = VectorNativeBackend(raw)

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
from httk.core.vectors import FracVector, VectorNumpyView

exact = VectorNumpyView([[1, 2], [3, 4]], dtype=numpy.int64)
assert exact.dtype == numpy.int64 and exact.tolist() == [[1, 2], [3, 4]]

rounded = VectorNumpyView(FracVector([["1/2", "3/2", "5/2", "7/2"]]), dtype=numpy.int64)
assert rounded.tolist() == [[0, 2, 2, 4]]          # half-even, not truncation
```

#### Registering a custom leaf codec

A leaf codec is a `LeafCodec` — a name, a `from_fraction(value, **options)` conversion from the
canonical `Fraction` hub, and an option validator — registered with `register_leaf_codec`. Once
registered it is usable through the `leaf=` hint like any built-in:

```python
import fractions
from httk.core.vectors import FracVector, LeafCodec, VectorNativeView, known_leaf_codecs, register_leaf_codec

def _to_percent(value: fractions.Fraction) -> str:
    return f"{float(value * 100):g}%"

def _no_options(options: dict) -> None:
    if options:
        raise ValueError("percent codec takes no options")

register_leaf_codec(LeafCodec("percent", _to_percent, _no_options))
assert "percent" in known_leaf_codecs()
assert VectorNativeView(FracVector([["1/4", "1/2"]]), leaf="percent") == (("25%", "50%"),)
```

### The numpy view: adoption, conversion, and shedding

numpy support is an optional dependency; install it with the extra:

```bash
pip install "httk-core[numpy]"
```

`VectorNumpyView` has two construction paths.

**Adoption (O(1), zero-copy).** A raw base-class `numpy.ndarray` of numeric dtype (integer,
float, or complex) is *adopted* when `dtype=` is omitted or matches: the view shares the array's
memory and preserves its dtype, and no element is scanned or converted. Both `unwrap()` and
`unview()` recover the original array object. Values that cannot enter the exact Fraction hub
(non-finite floats, complex numbers) fail only if and when an exact conversion is actually
requested. Because the adopted array is not copied, the no-mutation rule applies: do not mutate
it while the view is in use (see the borrowing lifetime contract in
{doc}`view_backend_pattern`).

```python
import numpy
from httk.core import unview, unwrap
from httk.core.vectors import VectorNumpyView

raw = numpy.arange(6, dtype=numpy.complex128)
view = VectorNumpyView(raw)                  # O(1), zero-copy, dtype preserved
assert numpy.shares_memory(view, raw)
assert unwrap(view) is raw
assert unview(view) is raw
```

**Conversion.** Any other input — an exact vector, a native sequence, or an explicit `dtype=`
change — is built from the backend's exact `fractions` interchange, `float64` by default. That is
the one lossy step (rationals become their nearest binary value), so a 3×3 exact cell matrix
converts to a float matrix identically to `FracVector.to_floats()`:

```python
import numpy
from httk.core.vectors import FracVector, VectorNumpyView

cell = FracVector([["8.04", "0.0", "0.0"],
                          ["0.0", "3.72", "0.0"],
                          ["0.0", "0.0", "7.38"]])

arr = VectorNumpyView(cell)               # a genuine float64 ndarray
assert isinstance(arr, numpy.ndarray)
assert arr.dtype == numpy.float64 and arr.shape == (3, 3)
assert arr.tolist() == cell.to_floats()   # same float matrix as to_floats()
```

**Operations shed the view.** Operators, ufuncs, NumPy-dispatched functions (`numpy.concatenate`,
`numpy.linalg.norm`, ...), reductions, and slicing on a `VectorNumpyView` return base-class
ndarrays — the wrapper never follows results into numeric hot loops, so after the first
operation there is no per-element or per-call overhead versus plain numpy. A residual numpy path
that still produces a `VectorNumpyView` (e.g. `.reshape()`, `.T`) yields a *backend-less* view:
its own array data is authoritative, it never unwraps to the source backend, and `unview()`
normalizes it to a base ndarray.

`unview(view)` sheds the wrapper without another copy: the adopted raw array on the adoption
path, the already-built presentation array on the conversion path. (`numpy.asarray(view)` gives
the same base-class result; note it may share the presentation storage — it is *shed*, not
*detached*.)

Going the other way, `VectorFracView(ndarray)` captures a float64 array's values as **exact**
binary rationals. A value that has genuinely passed through a raw float64 array therefore does not
return as its original decimal fraction — but `limit_denominator` recovers the intended small
rational:

```python
import numpy
from httk.core.vectors import FracVector, VectorNumpyView, VectorFracView

one_third = FracVector([["1/3"]])
plain = numpy.asarray(VectorNumpyView(one_third))      # a plain float64 array (may share storage)
back = VectorFracView(plain)                           # captures the binary rational exactly

assert back.simplify() != one_third                    # it is the float64 value of 1/3
assert back.limit_denominator(100).simplify() == one_third
```

(This mirrors the orientation-lossiness note for cell parameters in *httk-atomistic*.)

When numpy is not installed, the numpy backend and view are simply not registered (the numpy view
module subclasses `numpy.ndarray`, so it cannot even be imported without numpy). Everything else —
the exact library and the frac/native family — works unchanged, and dispatch just never selects a
numpy backend.

### The numeric presentation (`NumericVector`)

The backends above each commit to one container type. One level up sits a convenience presentation
for callers who do not need exact arithmetic and simply want plain numpy numbers to compute with.
`to_numeric(obj)` delivers exactly that, and `NumericVector` is the generic name for what comes out:
a base-class `float64` `numpy.ndarray` for a tensor, a plain `float` for a scalar (shape `()`) —
never a view subclass, never a 0-d array.

The numeric presentation is **numpy-backed**, so a caller always knows the concrete type it gets.
numpy is an optional dependency of *httk-core* (the `httk-core[numpy]` extra), so `to_numeric`
**requires numpy** and raises `ImportError` (naming the extra) when it is not installed — uniformly,
regardless of the input shape. The one exception is `to_numeric_scalar`, which converts a single
value to a `float`: that needs no numpy and so works unconditionally.

```python
import fractions
import numpy
from httk.core.vectors import FracVector, SurdVector, to_numeric, to_numeric_scalar

F = fractions.Fraction

cell = FracVector([["8.04", "0.0", "0.0"],
                          ["0.0", "3.72", "0.0"],
                          ["0.0", "0.0", "7.38"]])

# A tensor becomes a plain float64 ndarray (the base class, not a view subclass):
arr = to_numeric(cell)
assert type(arr) is numpy.ndarray
assert arr.dtype == numpy.float64
assert arr.tolist() == cell.to_floats()

# A scalar — an exact rational or radical — becomes a plain float, never a 0-d array:
assert to_numeric(F(1, 4)) == 0.25
assert type(to_numeric(SurdVector.sqrt_of(2))) is float

# to_numeric_scalar is the numpy-free single-value helper:
assert to_numeric_scalar("1/3") == to_numeric(F(1, 3))
```

Use `to_numeric` when you just want numpy numbers; reach for a specific view (`VectorNumpyView`,
`VectorNativeView`) when you need control over the exact container type, the numpy `dtype=`, or the
leaf codec. Relation to `unview`: `to_numeric` always *converts* to base-class `float64`, while
`unview(VectorNumpyView(...))` *sheds* — it preserves the view's dtype and is zero-copy.

### `unwrap` and `unview`

`unwrap(obj)` returns the most raw representation available: the wrapped `FracVector` for a frac
backend, the original nested sequence for a native backend, and the underlying `ndarray` for a
numpy backend. For anything that is not a view/backend it returns the object unchanged.

`unview(obj)` sheds a view wrapper sideways instead: a `VectorNativeView` becomes a plain
`tuple`, a `VectorFracView`/`VectorSurdView` a plain `FracVector`/`SurdVector` (reusing the
backend's object when it holds exactly the presented value), and a `VectorNumpyView` a base-class
`ndarray` without a copy. Non-view inputs pass through unchanged. See the four-verb table in
{doc}`view_backend_pattern`.
