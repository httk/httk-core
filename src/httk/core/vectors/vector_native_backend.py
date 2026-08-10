"""
Backend wrapping plain nested sequences (lists/tuples of numeric or string leaves).
"""

import decimal
import fractions
from typing import Any, Self

from .fracvector import FracVector
from .vector_api import Fractions
from .vector_backend import VectorBackend
from .vector_frac_backend import _fracvector_to_fractions

_LEAF_TYPES = (int, float, decimal.Decimal, fractions.Fraction, str)


def _is_native(obj: Any) -> bool:
    """
    Conservatively validate that ``obj`` is a rectangular (possibly nested) list/tuple whose
    leaves are all int/float/Decimal/Fraction/str.
    """
    if not isinstance(obj, (list, tuple)):
        return False
    return _valid(obj)


def _valid(node: Any) -> bool:
    if isinstance(node, (list, tuple)):
        if len(node) == 0:
            return True
        child_is_seq = isinstance(node[0], (list, tuple))
        length = len(node[0]) if child_is_seq else None
        for c in node:
            if isinstance(c, (list, tuple)) != child_is_seq:
                return False
            if child_is_seq and len(c) != length:
                return False
            if not _valid(c):
                return False
        return True
    return isinstance(node, _LEAF_TYPES)


class VectorNativeBackend(VectorBackend):
    r"""
    Backend for a vector backed by plain nested sequences.

    The native representation is a (possibly nested) rectangular list or tuple whose leaves are
    ``int``, ``float``, :class:`decimal.Decimal`, :class:`fractions.Fraction`, or ``str``.
    Conversion into the exact ``fractions`` interchange goes through
    :class:`~httk.core.vectors.fracvector.FracVector`, so string-uncertainty parsing
    (e.g. ``"0.33342(10)"``) works here too. ``unwrap`` returns the original raw object.

    :param obj: The rectangular source data to wrap.
    :param \**hints: Optional backend-selection hints.
    """

    _raw: Any
    _fracvector_cache: FracVector | None

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a native nested sequence when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if hints and hints.get("kind", "native") != "native":
            return None
        if not _is_native(obj):
            return None
        return cls(obj, **hints)

    def __init__(self, obj: Any, **hints: Any) -> None:
        self._raw = obj
        self._fracvector_cache = None

    @property
    def native(self) -> Any:
        """
        The original nested list/tuple this backend wraps, leaves untouched.

        This is the same object returned by :meth:`unwrap`, exposed as a named accessor so the
        native view can present a natively-held vector's leaves *verbatim* (its preserve-original
        default) without reaching into private state.
        """
        return self._raw

    def _as_fracvector(self) -> FracVector:
        if self._fracvector_cache is None:
            self._fracvector_cache = FracVector(self._raw)
        return self._fracvector_cache

    @property
    def fractions(self) -> Fractions:
        """Return the native value in the exact Fraction interchange format."""
        return _fracvector_to_fractions(self._as_fracvector())

    @property
    def dim(self) -> tuple[int, ...]:
        """Return the native value's shape."""
        return self._as_fracvector().dim

    def unwrap(self) -> Any:
        """Return the original nested list or tuple."""
        return self._raw
