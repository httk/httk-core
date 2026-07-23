"""
A view presenting any vector backend as nested tuples with exact leaves.
"""

from typing import Any, Self

from httk.core.views import unwrap

from .vector_api import Fractions
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_view import VectorView


def _to_native(node: Fractions) -> Any:
    """
    Convert the exact ``fractions`` interchange into nested tuples with exact leaves: an ``int``
    when the value is integral, otherwise a :class:`fractions.Fraction`. Never a float.
    """
    if isinstance(node, tuple):
        return tuple(_to_native(e) for e in node)
    if node.denominator == 1:
        return int(node)
    return node


class VectorNativeView(VectorView, tuple):
    """
    A view presenting an underlying vector backend as nested tuples.

    This view is a genuine (possibly nested) ``tuple`` with **exact** leaves: an ``int`` when
    the value is integral, otherwise a :class:`fractions.Fraction` — never a silent float. Users
    who want floats should use the numpy view or
    :meth:`~httk.core.vectors.fracvector.FracVector.to_floats`. A scalar source is presented as a
    single-element tuple.
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        native = _to_native(backend.fractions)
        if isinstance(native, tuple):
            instance = super().__new__(cls, native)
        else:
            instance = super().__new__(cls, (native,))
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, **hints: Any) -> None:
        super().__init__()

    def unwrap(self) -> Any:
        return unwrap(self._backend)
