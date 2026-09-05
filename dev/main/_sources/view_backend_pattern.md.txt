# Views and Backends

*httk₂* separates *what data is* from *how you want to work with it right now*.
A **backend** carries one representation of the data; a **view** presents a
backend through the interface you need; an **`XLike`** union names everything a
function accepts. The implied contract: **views are immutable access** — one
piece of data, read through as many formats as you like, all consistent. The
moment you need to *mutate*, you leave the view world, and how you leave it
matters (see below).

Inside a function you normalize once to the view that suits your algorithm and
write the logic against that view only:

```python
import numpy

from httk.core import FracVector, coerce_view
from httk.core.vectors import VectorFracView, VectorLike


def center(vector: VectorLike) -> VectorLike:
    view = VectorFracView(vector)      # normalize once: exact arithmetic inside
    result = view - view[0]
    return coerce_view(result, vector)  # answer in the caller's own kind


print(center(FracVector(["1/2", "2/3", "3/4"])))  # prints: (1/144)*(0, 24, 36)
print(center(numpy.array([0.5, 2 / 3, 0.75])))  # prints: [0.         0.16666667 0.25      ]
```

Four verbs cover every direction of movement:

- `unwrap(v)` — recover the original backend object, never a copy;
- `unview(v)` — shed the httk wrapper and get a plain value of the presented type;
- `coerce_view(v, t)` — best-effort re-presentation as `t`, keeping the exact backend behind view results;
- `coerce(v, t)` — strict: a plain instance of `t` or `TypeError`.

## Reading, mutating, and the cost of `unview`

**Example 1 — immutable multi-format access, the normal case.** Any number of
views over one backend read consistently; none of them copies eagerly:

```python
import numpy

from httk.core.vectors import VectorFracView, VectorNumpyView

array = numpy.array([[0.5, 0.0], [0.0, 0.25]])
view = VectorNumpyView(array)          # zero-copy adoption
exact = VectorFracView(view)           # same backend, exact presentation
assert exact[0, 0] == numpy.asarray(view)[0, 0] == 0.5
```

**Example 2 — mutation through `unview` expires the views.** `unview` removes
the httk wrapper; it does **not** detach. For the zero-copy numpy path the
result *is* the adopted storage:

```python
from httk.core import unview

shed = unview(view)
assert shed is array                   # the very same ndarray — no copy was made
```

Mutating `shed` (or `array`) now conceptually expires **every view aliasing
that storage** — here both `view` and `exact`. There is no runtime tracking:
a sibling view that has not yet converted will see the new value, one that
already cached its presentation will not. Treat any read from an expired view
as undefined; mutate only after the views built on that data are out of use.

**Example 3 — mutate a copy and keep the views valid.** When you need the
data mutable *and* the views alive, copy through the target representation's
own mechanism — this is the "`unview` but do not invalidate" pattern:

```python
independent = numpy.array(unview(view), copy=True)
independent[0, 0] = 99.0               # views on the original stay valid
assert exact[0, 0] == 0.5
```

There is deliberately no generic `unview_copy` verb: what "copy" means (deep
or shallow, dtype, layout) belongs to the target representation's own
vocabulary, and the presentations that are immutable by construction — native
nested tuples, `Fraction` leaves — carry no aliasing hazard in the first
place (`unview` of a native view returns a plain `tuple`; mutating means
building a list or array, which is already a copy). The hazard is
concentrated exactly where zero-copy sharing is: adopted and shed numpy
arrays.

For the full pattern — naming conventions, the verb semantics table, the
borrowing lifetime contract, shared stream state, and design guidance for new
domains — see {doc}`details/view_backend_pattern`.
