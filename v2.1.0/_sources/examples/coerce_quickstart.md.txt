# Coercion quickstart

Four verbs cover moving between httk views, backends, and plain values:

- ``coerce_view(value, target)`` is backend-aware: the result may be an httk view that retains
  the exact backend (recoverable with ``unwrap``).
- ``coerce(value, target)`` is strict: for non-View targets other than ``"natural"``, the result is a plain, non-view instance of the target; a View-class target deliberately returns a view.
- ``unview(value)`` sheds an httk view wrapper, keeping the presented representation.
- ``unwrap(value)`` recovers the original backend/source object.

A function that works with vectors can do its arithmetic exactly and hand the result back in the
caller's own kind: a numpy matrix in, a numpy-compatible result out.

```{literalinclude} ../../examples/coerce_quickstart.py
:language: python
:lines: 14-
```
