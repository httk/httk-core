"""
Backend wrapping a numpy ndarray (numpy is an optional dependency, imported lazily).
"""

import fractions
from typing import Any

from .vector_api import Fractions
from .vector_backend import VectorBackend


class VectorNumpy(VectorBackend):
    """
    Backend for a vector backed by a :class:`numpy.ndarray`.

    numpy is an optional dependency (``httk-core[numpy]``) and is imported lazily; if numpy is
    not installed, this backend's ``__new__`` returns None so it is simply never selected.

    numpy float64 values are themselves binary rationals, so the ``fractions`` interchange is
    produced *exactly* from the array (each float becomes its exact rational value). Only the
    reverse direction (building a numpy view) is lossy. ``unwrap`` returns the wrapped array.
    """

    _array: Any

    # Cannot type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: Any, **hints: Any) -> Any:
        if hints and hints.get("kind", "numpy") != "numpy":
            return None
        try:
            import numpy
        except ImportError:
            return None
        if not isinstance(obj, numpy.ndarray):
            return None
        return super().__new__(cls)

    def __init__(self, obj: Any, **hints: Any) -> None:
        self._array = obj

    @property
    def fractions(self) -> Fractions:
        def rec(x: Any) -> Fractions:
            if isinstance(x, list):
                return tuple(rec(e) for e in x)
            return fractions.Fraction(x)

        return rec(self._array.tolist())

    @property
    def dim(self) -> tuple[int, ...]:
        return tuple(self._array.shape)

    def unwrap(self) -> Any:
        return self._array
