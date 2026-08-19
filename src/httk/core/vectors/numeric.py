"""
The *numeric* presentation of vectors: plain numpy numbers for callers who just want floats.

Where the backend/view family (see :mod:`httk.core.vectors.vector_view`) lets the same tensor be
seen as the exact :class:`~httk.core.vectors.fracvector.FracVector`, an exact
:class:`~httk.core.vectors.surdvector.SurdVector`, a nested ``tuple``, or a
:class:`numpy.ndarray`, the **numeric** concept is a convenience presentation one level above that:
it is for users who do not care which representation carries the numbers and simply want plain
numpy floats to compute with.

The numeric presentation is **numpy-backed**, so a caller always knows the concrete type it gets:
:func:`to_numeric` returns a base-class ``float64`` :class:`numpy.ndarray` for a tensor and a plain
:class:`float` for a scalar — never a view subclass, never a 0-d array. :data:`NumericVector` is the
generic name for what comes out.

numpy is an optional dependency of *httk-core* (the ``httk-core[numpy]`` extra). :func:`to_numeric`
therefore **requires numpy** and raises :class:`ImportError` when it is not installed. The scalar
helper :func:`to_numeric_scalar` is the exception: converting a single value to a ``float`` needs no
numpy, so it works unconditionally and never raises for a missing numpy.

Use the numeric helpers when you just want numpy numbers; reach for a specific view
(:class:`~httk.core.vectors.vector_numpy_view.VectorNumpyView`,
:class:`~httk.core.vectors.vector_native_view.VectorNativeView`) when you need control over the exact
container type, dtype, or leaf codec.
"""

import fractions
from typing import TYPE_CHECKING, Any

from httk.core import exactmath
from httk.core.views import unwrap

from .fracvector import FracVectorBase
from .surdvector import SurdScalar, SurdVector
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_view import VectorView

if TYPE_CHECKING:
    import numpy

# PEP 695 type aliases are lazily evaluated, so the numpy.ndarray reference (numpy imported only
# under TYPE_CHECKING) is safe here: the alias value is not evaluated at runtime.
type NumericVector = float | numpy.ndarray

_NUMPY_REQUIRED_MESSAGE = "the numeric presentation requires numpy; install the httk-core[numpy] extra"


def numpy_available() -> bool:
    """
    Return whether the optional numpy dependency is available for the numeric helpers.

    This reads the vectors package's ``_numpy_available`` flag freshly on each call (the flag set
    when :mod:`httk.core.vectors` conditionally imports/registers the numpy backend), so tests may
    monkeypatch ``httk.core.vectors._numpy_available`` to exercise the numpy-absent path.

    :return: ``True`` when numpy is available, otherwise ``False``.
    """
    from httk.core import vectors

    return bool(vectors._numpy_available)


def _require_numpy() -> None:
    """Raise :class:`ImportError` (naming the ``httk-core[numpy]`` extra) if numpy is unavailable."""
    if not numpy_available():
        raise ImportError(_NUMPY_REQUIRED_MESSAGE)


def to_numeric_scalar(obj: Any) -> float:
    """
    Convert a single scalar value to a plain :class:`float`, deterministically.

    A :class:`~httk.core.vectors.surdvector.SurdScalar` (or scalar
    :class:`~httk.core.vectors.surdvector.SurdVector`) and a scalar
    :class:`~httk.core.vectors.fracvector.FracVector` render through their own exact
    ``to_float()``; a :class:`~fractions.Fraction`, ``int``, ``float``, or numeric ``str`` render via
    :func:`~httk.core.exactmath.any_to_fraction`. A non-scalar shape raises
    :class:`TypeError`.

    Unlike :func:`to_numeric`, this needs **no numpy**: a plain ``float`` conversion has no numpy
    dependency, so it works unconditionally and never raises for a missing numpy.

    :param obj: The scalar value to convert.
    :return: The converted scalar value.
    :raises TypeError: If ``obj`` is not scalar or cannot be converted to a scalar float.
    """
    if isinstance(obj, SurdScalar):
        return obj.to_float()
    if isinstance(obj, SurdVector):
        if obj.dim != ():
            raise TypeError(f"to_numeric_scalar: expected a scalar, got a SurdVector of shape {obj.dim}")
        return obj._as_scalar().to_float()
    if isinstance(obj, FracVectorBase):
        if obj.dim != ():
            raise TypeError(f"to_numeric_scalar: expected a scalar, got a FracVector of shape {obj.dim}")
        return obj.to_float()
    if isinstance(obj, (bool, int, float, str, fractions.Fraction)):
        return float(exactmath.any_to_fraction(obj))
    raise TypeError(f"to_numeric_scalar: cannot convert {type(obj).__name__} to a scalar float")


def to_numeric(obj: VectorLike | float | str | fractions.Fraction) -> NumericVector:
    """
    Present ``obj`` as plain numpy numbers: a :class:`numpy.ndarray` for a tensor, a ``float`` for a
    scalar.

    A tensor becomes a base-class ``float64`` :class:`numpy.ndarray` (never a view subclass) via
    :class:`~httk.core.vectors.vector_numpy_view.VectorNumpyView`; a **scalar** input (shape ``()``)
    returns a plain :class:`float` via :func:`to_numeric_scalar` (never a 0-d array).

    The numeric presentation is numpy-backed, so this **always requires numpy**: it raises
    :class:`ImportError` (naming the ``httk-core[numpy]`` extra) when numpy is not installed,
    uniformly, so the contract is predictable regardless of the input shape. Use
    :func:`to_numeric_scalar` directly for a single float without a numpy requirement.

    :param obj: The vector-like value to present numerically.
    :return: The converted scalar or tensor value.
    :raises ImportError: If numpy is unavailable.
    :raises TypeError: If the value cannot be converted to the numeric presentation.
    """
    _require_numpy()

    import numpy

    from .vector_numpy_view import VectorNumpyView

    # Bare Python scalars are not wrapped by the vector family; convert them directly.
    if isinstance(obj, (bool, int, float, str, fractions.Fraction)):
        return to_numeric_scalar(obj)

    # Everything else is family-representable: inspect its shape through a backend. A view built
    # through the low-level constructor path can be backend-less, so fall through to create.
    if isinstance(obj, VectorView) and getattr(obj, "_backend", None) is not None:
        backend = obj._backend
    elif isinstance(obj, VectorBackend):
        backend = obj
    else:
        backend = VectorBackend._select_backend(obj)

    if backend.dim == ():
        return to_numeric_scalar(unwrap(backend))

    # numpy.asarray drops the view subclass, yielding a plain base-class float64 ndarray.
    return numpy.asarray(VectorNumpyView(backend))
