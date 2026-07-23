"""
A view presenting any vector backend as a numpy ndarray (float64).

This module subclasses :class:`numpy.ndarray`, which happens at class-definition time, so it
cannot be imported at all unless numpy is installed. The package ``__init__`` guards its import
with ``try/except ImportError`` accordingly.
"""

from typing import Any, Self

import numpy

from httk.core.views import unwrap

from .vector_api import Fractions
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_view import VectorView


def _to_floats(node: Fractions) -> Any:
    if isinstance(node, tuple):
        return [_to_floats(e) for e in node]
    return float(node)


class VectorNumpyView(VectorView, numpy.ndarray):
    """
    A view presenting an underlying vector backend as a float64 :class:`numpy.ndarray`.

    This view is a genuine ndarray (built via ``numpy.asarray(...).view(cls)``), so it can be
    passed anywhere a numpy array is accepted. Building it is **lossy**: the exact rational
    values are converted to float64, so a value such as ``1/3`` becomes its nearest binary
    rational. Round-tripping back through the exact representation therefore recovers the float64
    rational, not the original ``1/3`` (use
    :meth:`~httk.core.vectors.fracvector.FracVector.limit_denominator` to recover a small
    denominator). numpy is an optional dependency (``httk-core[numpy]``).
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        arr = numpy.asarray(_to_floats(backend.fractions), dtype=numpy.float64)
        instance = arr.view(cls)
        instance._backend = backend
        return instance

    def __array_finalize__(self, obj: Any) -> None:
        # Propagate the backend reference to arrays derived from this view (slices, ufunc
        # results, ...). Derived arrays created outside our __new__ have no backend.
        if obj is None:
            return
        backend = getattr(obj, "_backend", None)
        if backend is not None:
            self._backend = backend

    def unwrap(self) -> Any:
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)
