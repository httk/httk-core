"""
The accepted-input union for vector functions.
"""

from typing import TYPE_CHECKING, Any

from . import fracvector, vector_backend, vector_view

if TYPE_CHECKING:
    import numpy

# PEP 695 type aliases are lazily evaluated, so the numpy.ndarray reference (numpy imported only
# under TYPE_CHECKING) is safe here: the alias value is not evaluated at runtime.
type VectorLike = (
    vector_backend.VectorBackend
    | vector_view.VectorView
    | fracvector.FracVector
    | tuple[Any, ...]
    | list[Any]
    | "numpy.ndarray"
)
