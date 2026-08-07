"""
The abstract base class for all vector views.
"""

from typing import ClassVar, Self

from httk.core.views import View

from .vector_backend import VectorBackend


class VectorView(View[VectorBackend]):
    """
    Abstract base class for all views of vector (tensor) data.

    Concrete views present a backend through a specific container or leaf domain while retaining
    access to the underlying backend.
    """

    _backend_base_cls: ClassVar[type[VectorBackend]] = VectorBackend  # type: ignore[type-abstract]
    _view_base_cls: ClassVar[type[Self]]


VectorView._view_base_cls = VectorView
