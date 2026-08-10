"""
A view presenting any vector backend as a SurdVector (the exact squarefree-radical representation).
"""

from functools import cached_property
from typing import Any, Self

from httk.core.views import unwrap

from .fracvector import FracVector
from .surdvector import SurdVector
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_view import VectorView


class VectorSurdView(VectorView, SurdVector):
    r"""
    A view presenting an underlying vector backend as an exact
    :class:`~httk.core.vectors.surdvector.SurdVector`.

    This view is a genuine SurdVector, so it exposes the full exact surd algebra
    (``det``/``inv``/``*``/``length``/``...). It is built lazily on first access, following the
    immutable-subclass pattern of
    :class:`~httk.core.vectors.vector_frac_view.VectorFracView`: from a surd backend it adopts the
    exact SurdVector directly, and from a frac/native/numpy backend it embeds the backend's exact
    rational ``fractions`` at radicand 1 — exactly, since every rational is a surd.

    (numpy values are binary rationals, so a numpy source embeds the exact float64 rational, not
    necessarily the original decimal fraction — the same caveat as
    :class:`~httk.core.vectors.vector_frac_view.VectorFracView`.)

    :param obj: The source value to present.
    :param \**hints: Backend-selection and view-conversion hints.
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        instance = object.__new__(cls)
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, **hints: Any) -> None:
        pass

    def _fill_fractions(self) -> None:
        # Validate then assign: failed fills leave no partial presentation state, and fills must
        # not read shadowed attributes or they recurse.
        if "_backend" not in self.__dict__:
            return
        backend = self._backend
        if isinstance(backend, SurdVector):
            surd = backend
        else:
            surd = SurdVector(backend.fractions)
        SurdVector._set_components(self, surd._components, surd._dim)

    def _ensure_materialized(self) -> None:
        if "_backend" in self.__dict__ and "_components" not in self.__dict__:
            self._fill_fractions()

    @cached_property
    def _components(self) -> dict[int, FracVector]:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["_components"]

    @cached_property
    def _dim(self) -> tuple[int, ...]:  # type: ignore[override]  # pyright: ignore[reportIncompatibleVariableOverride]
        self._fill_fractions()
        return self.__dict__["_dim"]

    def unwrap(self) -> Any:
        """Return the underlying unwrapped vector, or this value when no backend remains."""
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)

    def unview(self) -> Any:
        """Return a plain SurdVector containing this view's presented data."""
        # A surd backend already holds exactly the presented SurdVector: reuse it. Otherwise
        # build a plain SurdVector reusing the materialized components mapping.
        backend = getattr(self, "_backend", None)
        if isinstance(backend, SurdVector):
            raw = backend
            if not isinstance(raw, VectorView):
                return raw
        return SurdVector.from_components(self._components, self._dim)
