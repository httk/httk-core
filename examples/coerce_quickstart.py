"""Coercion quickstart

``coerce(value, target)`` returns a value as a requested class, or matching a prototype instance.
A function that works with vectors can do its arithmetic exactly and hand the result back in the
caller's own kind: a numpy matrix in, a numpy-compatible view out.
"""

import numpy

from httk.core import coerce
from httk.core.vectors import VectorFracView, VectorNumpyView


def halve(vector):
    exact = VectorFracView(vector) / 2
    return coerce(exact, vector)


matrix = numpy.array([[1.0, 2.0], [3.0, 4.0]])
result = halve(matrix)
assert type(result) is VectorNumpyView
assert isinstance(result, numpy.ndarray)
print(type(result).__name__)
print(isinstance(result, numpy.ndarray))
print(result)
