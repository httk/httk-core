"""
A view presenting any vector backend as a SurdVector (the exact squarefree-radical representation).
"""

from typing import Any, Self

from httk.core.views import unwrap

from .surdvector import SurdVector
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_surd import VectorSurd
from .vector_view import VectorView


class VectorSurdView(VectorView, SurdVector):
    """
    A view presenting an underlying vector backend as an exact
    :class:`~httk.core.vectors.surdvector.SurdVector`.

    This view is a genuine SurdVector, so it exposes the full exact surd algebra
    (``det``/``inv``/``*``/``length``/...). It is built **eagerly** on construction, following the
    eager immutable-subclass pattern of
    :class:`~httk.core.vectors.vector_frac_view.VectorFracView`: from a surd backend it adopts the
    exact SurdVector directly, and from a frac/native/numpy backend it embeds the backend's exact
    rational ``fractions`` at radicand 1 — exactly, since every rational is a surd.

    (numpy values are binary rationals, so a numpy source embeds the exact float64 rational, not
    necessarily the original decimal fraction — the same caveat as
    :class:`~httk.core.vectors.vector_frac_view.VectorFracView`.)
    """

    _backend: VectorBackend

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        if isinstance(obj, cls):
            return obj
        backend = cls._prepare_backend(obj, hints)
        if isinstance(backend, VectorSurd):
            surd = backend.unwrap()
        else:
            surd = SurdVector.create(backend.fractions)
        instance = super().__new__(cls)
        # SurdVector state is initialized here in __new__ (keeping __init__ a no-op) so that
        # rewrapping an existing view via cls(view) does not re-initialize it.
        SurdVector.__init__(instance, surd._components, surd._dim)
        instance._backend = backend
        return instance

    def __init__(self, obj: VectorLike, **hints: Any) -> None:
        pass

    def unwrap(self) -> Any:
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)
