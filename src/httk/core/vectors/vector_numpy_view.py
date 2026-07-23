"""
A view presenting any vector backend as a numpy ndarray, with a selectable dtype.

This module subclasses :class:`numpy.ndarray`, which happens at class-definition time, so it
cannot be imported at all unless numpy is installed. The package ``__init__`` guards its import
with ``try/except ImportError`` accordingly.
"""

from typing import Any, Self

import numpy

from httk.core.views import unwrap

from .leaf_codecs import apply_leaf_codec, leaf_codec_for_name
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
    A view presenting an underlying vector backend as a :class:`numpy.ndarray`, ``float64`` by
    default and any real numpy ``dtype=`` on request.

    This view is a genuine ndarray (built via ``numpy.asarray(...).view(cls)``), so it can be passed
    anywhere a numpy array is accepted. For a **float** dtype (the default ``float64``) building it
    is lossy-by-design: exact rational values become their nearest binary value, so ``1/3`` becomes
    a binary rational and round-tripping recovers that binary rational, not the original ``1/3`` (use
    :meth:`~httk.core.vectors.fracvector.FracVector.limit_denominator` to recover a small
    denominator). For an **integer** dtype each element is first converted through the ``"int"`` leaf
    codec's default (nearest, ties to even) via the exact Fraction hub — so a value such as ``1/2``
    becomes ``0`` by half-even rounding rather than being silently truncated by numpy. numpy is an
    optional dependency (``httk-core[numpy]``).
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        dtype = hints.pop("dtype", None)
        backend = cls._prepare_backend(obj, hints)
        np_dtype = numpy.dtype(numpy.float64 if dtype is None else dtype)
        if numpy.issubdtype(np_dtype, numpy.integer):
            # Round through the int codec via the exact Fraction hub BEFORE array construction, so
            # numpy casts already-integral Python ints (no silent truncation of fractional values).
            data = apply_leaf_codec(leaf_codec_for_name("int"), backend.fractions)
        else:
            data = _to_floats(backend.fractions)
        arr = numpy.asarray(data, dtype=np_dtype)
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
