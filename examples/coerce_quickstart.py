"""Coercion quickstart

Four verbs cover moving between httk views, backends, and plain values:

- ``coerce_view(value, target)`` is backend-aware: the result may be an httk view that retains
  the exact backend (recoverable with ``unwrap``).
- ``coerce(value, target)`` is strict: the result is a plain, non-view instance of the target.
- ``unview(value)`` sheds an httk view wrapper, keeping the presented representation.
- ``unwrap(value)`` recovers the original backend/source object.

A function that works with vectors can do its arithmetic exactly and hand the result back in the
caller's own kind: a numpy matrix in, a numpy-compatible result out.
"""

import numpy

from httk.core import coerce, coerce_view, unview, unwrap
from httk.core.vectors import VectorFracView, VectorNumpyView


def halve(vector):
    exact = VectorFracView(vector) / 2
    return coerce_view(exact, vector)


matrix = numpy.array([[1.0, 2.0], [3.0, 4.0]])
result = halve(matrix)
# coerce_view keeps the httk view: a genuine ndarray, with the exact backend retained.
assert type(result) is VectorNumpyView
assert isinstance(result, numpy.ndarray)
assert isinstance(unwrap(result), VectorFracView)
# unview sheds the wrapper to a plain base-class ndarray (no extra copy).
plain = unview(result)
assert type(plain) is numpy.ndarray
# coerce does both steps at once: a plain instance of the requested target, or TypeError.
strict = coerce(VectorFracView(matrix) / 2, numpy.ndarray)
assert type(strict) is numpy.ndarray
print(type(result).__name__)
print(type(plain).__name__)
print(strict)
