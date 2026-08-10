"""
The abstract base class for all vector backends.
"""

from typing import Any, ClassVar

from httk.core.views import Backend

from .vector_api import VectorAPI


class VectorBackend(Backend["VectorBackend"], VectorAPI):
    """
    Abstract base class for all backends of vector (tensor) data.

    Concrete backends carry a native representation (an exact FracVector, plain nested
    sequences, or a numpy array) and produce the canonical exactness-preserving ``fractions``
    interchange declared by :class:`~httk.core.vectors.vector_api.VectorAPI` from it.

    Concrete subclasses select the accepted input and optional dispatch hints in their
    ``_backend_adopt`` hooks.
    """

    backend_classes: ClassVar[list[type[Backend[Any]]]]
