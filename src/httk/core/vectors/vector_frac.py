"""
Backend wrapping a FracVector/FracScalar in the exact-rational representation.
"""

import fractions
from typing import Any

from .fracvector import FracVector
from .vector_api import Fractions
from .vector_backend import VectorBackend


def _fracvector_to_fractions(fv: FracVector) -> Fractions:
    denom = fv.denom

    def rec(noms: Any) -> Fractions:
        if isinstance(noms, tuple):
            return tuple(rec(n) for n in noms)
        return fractions.Fraction(noms, denom)

    return rec(fv.noms)


class VectorFrac(VectorBackend):
    r"""
    Backend for a vector backed by an actual :class:`~httk.core.vectors.fracvector.FracVector`
    (or :class:`~httk.core.vectors.fracvector.FracScalar`).

    Its ``fractions`` accessor produces the exact nested tuple of Fraction, and ``unwrap``
    returns the wrapped FracVector.

    :param obj: The exact-rational value to wrap.
    :param \**hints: Optional backend-selection hints.
    """

    _fracvector: FracVector

    # Cannot type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: Any, **hints: Any) -> Any:
        if not isinstance(obj, FracVector):
            return None
        if hints and hints.get("kind", "frac") != "frac":
            return None
        return super().__new__(cls)

    def __init__(self, obj: FracVector, **hints: Any) -> None:
        self._fracvector = obj

    @property
    def fractions(self) -> Fractions:
        """Return the wrapped value in the exact Fraction interchange format."""
        return _fracvector_to_fractions(self._fracvector)

    @property
    def dim(self) -> tuple[int, ...]:
        """Return the wrapped vector's shape."""
        return self._fracvector.dim

    def unwrap(self) -> Any:
        """Return the wrapped FracVector or FracScalar."""
        return self._fracvector
