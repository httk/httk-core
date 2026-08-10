"""
Backend wrapping a numpy ndarray (numpy is an optional dependency, imported lazily).
"""

import fractions
from typing import Any, Self

from .vector_api import Fractions
from .vector_backend import VectorBackend


def _is_real_numeric(dtype: Any) -> bool:
    import numpy

    return any(numpy.issubdtype(dtype, kind) for kind in (numpy.bool_, numpy.integer, numpy.floating))


class VectorNumpyBackend(VectorBackend):
    r"""
    Backend for a vector backed by a :class:`numpy.ndarray`.

    numpy is an optional dependency (``httk-core[numpy]``) and is imported lazily; if numpy is
    not installed, this backend's ``_backend_adopt`` returns None so it is simply never selected.

    numpy float64 values are themselves binary rationals, so the ``fractions`` interchange is
    produced *exactly* from the array (each float becomes its exact rational value). Only the
    reverse direction (building a numpy view) is lossy. ``unwrap`` returns the wrapped array.

    :param obj: The source data to wrap.
    :param \**hints: Optional backend-selection hints.
    """

    _array: Any

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a numpy array when numpy is available and hints match.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if hints and hints.get("kind", "numpy") != "numpy":
            return None
        try:
            import numpy
        except ImportError:
            return None
        if not isinstance(obj, numpy.ndarray):
            return None
        return cls(obj, **hints)

    def __init__(self, obj: Any, **hints: Any) -> None:
        self._array = obj

    @property
    def fractions(self) -> Fractions:
        """Return the array in the exact Fraction interchange format."""

        def rec(x: Any) -> Fractions:
            if isinstance(x, list):
                return tuple(rec(e) for e in x)
            return fractions.Fraction(x)

        return rec(self._array.tolist())

    @property
    def dim(self) -> tuple[int, ...]:
        """Return the array shape."""
        return tuple(self._array.shape)

    def to_floats(self) -> Any:
        """Return floats through a numpy fast path for real numeric dtypes.

        Other dtypes fall back to :meth:`VectorAPI.to_floats` so the exact hub conversion and
        its error semantics are preserved.

        :return: The rendered value.
        """
        if _is_real_numeric(self._array.dtype):
            return self._array.astype(float).tolist()
        return super().to_floats()

    def to_float(self) -> float:
        """Return a scalar float through numpy for real numeric 0-D arrays.

        Non-scalar arrays raise the same :class:`TypeError` as the hub implementation. Other
        scalar dtypes fall back to :meth:`VectorAPI.to_float` for its exact conversion and error
        semantics.

        :return: The rendered scalar value.
        :raises TypeError: If the value is not scalar.
        """
        if self.dim != ():
            raise TypeError(f"to_float: expected a scalar, got shape {self.dim}")
        if _is_real_numeric(self._array.dtype):
            return float(self._array)
        return super().to_float()

    def unwrap(self) -> Any:
        """Return the wrapped numpy array."""
        return self._array
