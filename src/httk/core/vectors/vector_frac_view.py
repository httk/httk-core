"""
A view presenting any vector backend as a FracVector (the exact-rational representation).
"""

from functools import cached_property
from typing import Any, Self

from httk.core.views import unwrap

from .fracvector import FracVector, Noms
from .vector_backend import VectorBackend
from .vector_frac import VectorFrac
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
    lazily on first access — adopting a frac backend's FracVector directly, otherwise
    converting from the backend's exact ``fractions`` interchange — so the
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
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, denom: Any = _NO_DENOM, **hints: Any) -> None:
        pass

    def _fill_fractions(self) -> None:
        # Validate then assign: failed fills leave no partial presentation state, and fills must
        # not read shadowed attributes or they recurse.
        if isinstance(self._backend, VectorFrac):
            built = self._backend.unwrap()
        else:
            built = FracVector.create(self._backend.fractions)
        FracVector.__init__(self, built.noms, built.denom)

    def _ensure_materialized(self) -> None:
        if "_backend" in self.__dict__ and "noms" not in self.__dict__:
            self._fill_fractions()

    @cached_property
    def noms(self) -> Noms:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["noms"]

    @cached_property
    def denom(self) -> int:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["denom"]

    @cached_property
    def _dim(self) -> tuple[int, ...] | None:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["_dim"]

    def unwrap(self) -> Any:
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)
