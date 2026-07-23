"""
A view presenting any vector backend as a FracVector (the exact-rational representation).
"""

from typing import Any, Self

from httk.core.views import unwrap

from .fracvector import FracVector
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_view import VectorView

# Sentinel distinguishing the two ways this class is constructed (see __new__).
_NO_DENOM: Any = object()


class VectorFracView(VectorView, FracVector):
    """
    A view presenting an underlying vector backend as an exact
    :class:`~httk.core.vectors.fracvector.FracVector`.

    This view is a genuine FracVector, so it can be passed anywhere a FracVector is accepted,
    and it exposes the full exact-rational algebra (``det``/``inv``/``*``/...). It is built
    eagerly from the backend's exact ``fractions`` interchange on construction, so the
    round-trip is exactness-preserving for the frac and native backends. (numpy values are
    binary rationals, so a numpy source round-trips to the exact float64 rational, not
    necessarily the original decimal fraction.)

    Because inherited FracVector algebra builds its results with the low-level
    ``self.__class__(noms, denom)`` constructor, this class also accepts that two-argument form;
    results built that way are plain (backend-less) FracVector values presented through this
    class.
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, denom: Any = _NO_DENOM, **hints: Any) -> Self:
        if denom is not _NO_DENOM:
            # Low-level FracVector construction: VectorFracView(noms, denom). Results built this
            # way by inherited algebra are plain (backend-less) FracVector values; _backend is
            # left unset (see unwrap).
            instance = super().__new__(cls)
            FracVector.__init__(instance, obj, denom)  # type: ignore[arg-type]
            return instance
        # View-building path: VectorFracView(vector_like, **hints)
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = super().__new__(cls)
        # FracVector state is initialized here in __new__ (keeping __init__ a no-op), so that
        # rewrapping an existing view via cls(view) does not re-initialize it.
        built = FracVector.create(backend.fractions)
        FracVector.__init__(instance, built.noms, built.denom)
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, denom: Any = _NO_DENOM, **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)
