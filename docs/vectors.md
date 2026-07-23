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
print(recip.noms, recip.denom)   # ((3431700, 0, 0), (0, 7416900, 0), (0, 0, 3738600)) 27590868
```

A few essentials:

- `FracVector.create(...)` accepts nested lists/tuples of ints, floats, `Decimal`,
  `fractions.Fraction`, and strings; `.noms`/`.denom` expose the raw representation, and equality
  (`==`) compares *numerical* value, so `FracVector([[1]], 2) == FracVector([[2]], 4)`.
- Most operations deliberately return an **un-simplified** result (they do not reduce to the
  smallest denominator). Call `.simplify()` at the end of a computation when you want the reduced
  form. This keeps intermediate arithmetic cheap while staying exact.
- `*` is **matrix multiplication**; `+`/`-`/`/` are element-wise; `A ** -1` is the matrix inverse
  (`A.inv()`). Other staples: `det()` (3×3 and 4×4), `T()`, `dot()`, `cross()`, `lengthsqr()`,
  `metric_product()`, `normalize()`/`normalize_half()`.

```python
a = FracVector.create([[2, 3, 5], [3, 5, 4], [4, 6, 7]])
assert a.det() == -3
assert (a * a.inv()).simplify() == FracVector.eye((3, 3))

# Laziness: results stay un-simplified until you ask.
third = FracVector.create("1/3")
assert (third * 3).simplify() == 1
```

`FracScalar` is the scalar specialization (a single `nom/denom`). `MutableFracVector` is a
list-backed variant that additionally supports in-place element assignment (`m[2, 1:] = [4, 5]`)
and `set_*` mutators (`set_T`, `set_inv`, `set_simplify`, ...); its inherited (non-`set_`) methods
still return copies.

### Creation from strings and uncertainties

String input is parsed for significant digits, so a written decimal is taken at its stated
precision rather than as an exact binary float:

```python
FracVector.create("0.33")          # -> 33/100  (0.33 assumed to mean 0.3300)
FracVector.create("0.3333")        # -> 1/3     (enough digits to imply 1/3)
FracVector.create("0.33", min_accuracy=None)  # -> 33/100, converted exactly
FracVector.create(["0.33342(10)"]) # -> 1/3, using the explicit standard deviation
```

Note that a Python **float literal** is a binary rational, so `FracVector.create([8.04])` stores
`fractions.Fraction(8.04)` (a large denominator), *not* `804/100`. Use the string form `"8.04"`
(or an explicit `Decimal`) when you mean the decimal value.

The exact transcendental helpers live in `httk.core.vectors.fracmath` (rational approximations of
`sqrt`/`cos`/`sin`/`exp`/`pi`/... on `fractions.Fraction`), and `httk.core.vectors.vectormath`
provides `math`-style functional wrappers that dispatch to a FracVector's own methods when given
one and fall back to `math` otherwise.

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
from httk.core import VectorFracView, VectorNativeView, VectorBackend

# Dispatch by input type:
VectorBackend.create([[1, 2], [3, 4]])                       # -> VectorNative
VectorBackend.create(FracVector.create([[1, 2], [3, 4]]))    # -> VectorFrac

# A frac view is a genuine FracVector, so the full exact algebra is available:
VectorFracView([[2, 3, 5], [3, 5, 4], [4, 6, 7]]).det()      # -> -3

# A native view is a genuine nested tuple with exact leaves (int when integral, else Fraction):
VectorNativeView([["1/3", "2/3"]])                           # -> ((Fraction(1, 3), Fraction(2, 3)),)
```

The canonical interchange between representations is **exactness-preserving**: every backend
exposes `.fractions` (a nested tuple of `fractions.Fraction`, or a bare `Fraction` for a scalar)
and `.dim`. Because numpy float64 values are themselves binary rationals, even a numpy array
produces `.fractions` *exactly*.

### Lossiness

Only building a **numpy view** is lossy — that is the one step that leaves the rationals for
float64:

| conversion                         | exact? | note                                                       |
| ---------------------------------- | ------ | ---------------------------------------------------------- |
| frac ↔ native                      | yes    | integers stay `int`, non-integers stay `Fraction`          |
| frac/native → `.fractions`         | yes    | the shared exact interchange                               |
| numpy array → `.fractions`         | yes    | float64 values are exact binary rationals                  |
| → numpy **view** (float64)         | **no** | rationals such as `1/3` become their nearest binary value  |

So a value that has genuinely passed through a raw float64 array does not return as its original
decimal fraction, but `limit_denominator` recovers the intended small rational:

```python
import numpy
from httk.core import VectorNumpyView, VectorFracView

one_third = FracVector.create([["1/3"]])
detached = numpy.asarray(VectorNumpyView(one_third))   # a plain float64 array
back = VectorFracView(detached)
assert back.simplify() != one_third                    # it is the float64 binary rational
assert back.limit_denominator(100).simplify() == one_third
```

(This mirrors the orientation-lossiness note for cell parameters in *httk-atomistic*.)

### The numpy extra

numpy support is an optional dependency. Install it with the extra:

```bash
pip install "httk-core[numpy]"
```

When numpy is not installed, the numpy backend and view are simply not registered (the numpy view
module subclasses `numpy.ndarray`, so it cannot even be imported without numpy). Everything else —
the exact library and the frac/native family — works unchanged, and dispatch just never selects a
numpy backend.

## `unwrap`

`unwrap(obj)` returns the most raw representation available: the wrapped `FracVector` for a frac
backend, the original nested sequence for a native backend, and the underlying `ndarray` for a
numpy backend. For anything that is not a view/backend it returns the object unchanged.
