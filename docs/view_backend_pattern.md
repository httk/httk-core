# Views and Backends

*httk₂* separates *what data is* from *how you want to work with it right now*.
A **backend** carries one representation of the data; a **view** presents a
backend through the interface you need; an **`XLike`** union names everything a
function accepts. Inside a function you normalize once to the view that suits
your algorithm and write the logic against that view only:

```python
from httk.core import coerce_view
from httk.core.vectors import VectorFracView, VectorLike


def center(vector: VectorLike) -> VectorLike:
    view = VectorFracView(vector)      # normalize once: exact arithmetic inside
    result = view - view[0]
    return coerce_view(result, vector)  # answer in the caller's own kind
```

The caller can pass a nested list, a `FracVector`, or a numpy view — the
function does not care, and the exact result stays recoverable through
`unwrap()` on what it returns.

Four verbs cover every direction of movement:

- `unwrap(v)` — recover the original backend object, never a copy;
- `unview(v)` — shed the httk wrapper and get a plain value of the presented type;
- `coerce_view(v, t)` — best-effort re-presentation as `t`, keeping the exact backend behind view results;
- `coerce(v, t)` — strict: a plain instance of `t` or `TypeError`.

Views are usually lazy and *borrow* their inputs: do not mutate data that a
view is built on. For the full pattern — naming conventions, the verb
semantics table, aliasing and the borrowing lifetime contract, and design
guidance for new domains — see {doc}`details/view_backend_pattern`.
