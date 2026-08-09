# Vectors

`httk.core.vectors` works with tensors in the representation you choose:
plain nested sequences, numpy arrays, or exact values. Pick a presentation
and go:

```python
import numpy

from httk.core.vectors import VectorNativeView, VectorNumpyView, to_numeric

values = [["1/3", 2], ["3/4", 4]]
floats = VectorNativeView(values, leaf="float")  # nested tuples of plain floats
array = VectorNumpyView(values)                  # float64 ndarray
numeric = to_numeric(values)                     # ndarray for a tensor, float for a scalar

assert floats[0][0] == 1 / 3 and isinstance(array, numpy.ndarray)
```

Float presentations are convenient but lossy. When the values themselves must
survive arithmetic unchanged, work exact-first: `FracVector` is an immutable
tensor of exact rationals, with exact linear algebra (determinants, inverses,
metric products) and no floating point anywhere:

```python
from httk.core.vectors import FracVector

cell = FracVector.create([["1/2", 0, 0], [0, "1/3", 0], [0, 0, 2]])
identity = FracVector.create([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
assert (cell * cell.inv()).simplify() == identity
```

Every representation is a member of one view family (see
{doc}`view_backend_pattern`): build any view from any member, and `unwrap()`
recovers the exact original.

The full guide, {doc}`details/vectors`, covers creation from every numeric
type, the laziness/`simplify` contract, `MutableFracVector`, exact radicals
(`SurdVector` — hexagonal bases, exact degree trigonometry), leaf codecs
(`"float"`, `"decimal"`, custom), zero-copy numpy adoption and shedding, and
the `NumericVector` presentation.
