"""
A view presenting any vector backend as a FracVector (the exact-rational representation).
"""

from functools import cached_property
from typing import Any, Self

from httk.core.views import unwrap

from .fracvector import FracVector, Noms
from .vector_backend import VectorBackend
from .vector_frac import VectorFracBackend
from .vector_like import VectorLike
from .vector_view import VectorView


class VectorFracView(VectorView, FracVector):
    r"""
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
    ``self.__class__.from_noms_and_denom(noms, denom)`` constructor, results built that way are
    plain (backend-less) FracVector values presented through this class.

    :param obj: The source value to present.
    :param \**hints: Backend-selection and view-conversion hints.
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = super().__new__(cls)
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, **hints: Any) -> None:
        pass

    def _fill_fractions(self) -> None:
        # Validate then assign: failed fills leave no partial presentation state, and fills must
        # not read shadowed attributes or they recurse.
        if isinstance(self._backend, VectorFracBackend):
            built = self._backend.unwrap()
        else:
            built = FracVector(self._backend.fractions)
        FracVector._assign_raw(self, built.noms, built.denom)

    def _ensure_materialized(self) -> None:
        if "_backend" in self.__dict__ and "noms" not in self.__dict__:
            self._fill_fractions()

    @cached_property
    def noms(self) -> Noms:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the materialized numerator data."""
        self._fill_fractions()
        return self.__dict__["noms"]

    @cached_property
    def denom(self) -> int:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the materialized common denominator."""
        self._fill_fractions()
        return self.__dict__["denom"]

    @cached_property
    def _dim(self) -> tuple[int, ...] | None:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["_dim"]

    def unwrap(self) -> Any:
        """Return the underlying unwrapped vector, or this value when no backend remains."""
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)

    def unview(self) -> Any:
        """Return a plain FracVector containing this view's presented data."""
        # A frac backend already holds exactly the presented FracVector: reuse it. Otherwise
        # (converted or backend-less) build a plain FracVector reusing the materialized tuples.
        backend = getattr(self, "_backend", None)
        if isinstance(backend, VectorFracBackend):
            raw = backend.unwrap()
            if not isinstance(raw, VectorView):
                return raw
        return FracVector.from_noms_and_denom(self.noms, self.denom)
