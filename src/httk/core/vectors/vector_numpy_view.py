"""
A view presenting any vector backend as a numpy ndarray, with a selectable dtype.

This module subclasses :class:`numpy.ndarray`, which happens at class-definition time, so it
cannot be imported at all unless numpy is installed. The package ``__init__`` guards its import
with ``try/except ImportError`` accordingly.
"""

import copy
import copyreg
from typing import Any, Self, cast

import numpy

from httk.core.views import unwrap

from .leaf_codecs import apply_leaf_codec, leaf_codec_for_name
from .vector_api import Fractions
from .vector_backend import VectorBackend
from .vector_like import VectorLike
from .vector_native_backend import VectorNativeBackend
from .vector_numpy_backend import VectorNumpyBackend
from .vector_view import VectorView

_BACKEND_STATE_TAG = "httk-vector-backend"


def _to_floats(node: Fractions) -> Any:
    if isinstance(node, tuple):
        return [_to_floats(e) for e in node]
    return float(node)


def _shed(node: Any) -> Any:
    """Recursively replace VectorNumpyView instances with base-class ndarrays in args/kwargs."""
    if isinstance(node, VectorNumpyView):
        return node.view(numpy.ndarray)
    if isinstance(node, tuple):
        return tuple(_shed(e) for e in node)
    if isinstance(node, list):
        return [_shed(e) for e in node]
    if isinstance(node, dict):
        return {k: _shed(v) for k, v in node.items()}
    return node


def _rebuild_backend(backend_cls: type, value: Any) -> Any:
    return backend_cls(value)


def _reduce_backend(backend: VectorBackend) -> Any:
    return _rebuild_backend, (type(backend), unwrap(backend))


for _backend_cls in (VectorNumpyBackend, VectorNativeBackend):
    copyreg.pickle(_backend_cls, _reduce_backend)


class VectorNumpyView(VectorView, numpy.ndarray):
    r"""
    A view presenting an underlying vector backend as a :class:`numpy.ndarray`.

    This view is a genuine ndarray, so it can be passed anywhere a numpy array is accepted.
    Construction has two paths:

    - **Adoption (O(1), zero-copy).** A raw base-class :class:`numpy.ndarray` of numeric dtype
      (integer, float, or complex — not bool/object) is adopted directly when ``dtype=`` is
      omitted, ``None``, or equal to the array's dtype: the view shares the array's memory and
      preserves its dtype, no element is scanned or converted, and both ``unwrap()`` and
      ``unview()`` recover the original array object. Values that cannot enter the exact
      Fraction hub (non-finite floats, complex numbers) fail only if and when an exact
      conversion is actually requested (e.g. ``.fractions``). The adopted array is not copied,
      so the httk no-mutation rule applies: do not mutate it while the view is in use.
    - **Conversion.** Any other input — a non-ndarray source, or an explicit ``dtype=`` change —
      is built from the backend's exact ``fractions`` interchange: ``float64`` by default
      (lossy-by-design: exact rationals become their nearest binary value), and for an
      **integer** dtype each element is first converted through the ``"int"`` leaf codec's
      default (nearest, ties to even) so a value such as ``1/2`` becomes ``0`` by half-even
      rounding rather than being silently truncated by numpy. The original backend remains
      recoverable via ``unwrap()``.

    Common numpy operations **shed the view**: operators, ufuncs, NumPy-dispatched functions,
    reductions, and slicing return base-class ndarrays, so hot numeric loops carry no wrapper
    overhead past the first operation. A residual path that still produces a
    ``VectorNumpyView`` (e.g. ``.reshape()``/``.T``) yields a *backend-less* view whose own
    array data is authoritative; it never falsely unwraps to the source backend and is
    normalized with :func:`~httk.core.unview`. numpy is an optional dependency
    (``httk-core[numpy]``).

    :param obj: The source value to present numerically.
    :param \**hints: Backend-selection hints and an optional ``dtype`` conversion.
    """

    _backend: VectorBackend
    # Route copy.copy through __reduce_ex__ so the backend survives.
    __copy__ = None  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]

    def __new__(cls, obj: VectorLike, **hints: Any) -> Self:
        dtype = hints.pop("dtype", None)
        if isinstance(obj, cls):
            if dtype is None or numpy.dtype(dtype) == obj.dtype:
                return obj
            if getattr(obj, "_backend", None) is None:
                # A backend-less derived view converting to another dtype: its own data is
                # authoritative, so convert from the base array, not a source backend.
                obj = obj.view(numpy.ndarray)
        if (
            type(obj) is numpy.ndarray
            and obj.dtype.kind in "iufc"
            and (dtype is None or numpy.dtype(dtype) == obj.dtype)
            and hints.get("kind", "numpy") == "numpy"
        ):
            # Zero-copy adoption: share the array's memory and preserve its dtype.
            instance = obj.view(cls)
            instance._backend = VectorNumpyBackend(obj)
            return instance
        backend = cls._prepare_backend(obj, hints)
        np_dtype = numpy.dtype(numpy.float64 if dtype is None else dtype)
        if numpy.issubdtype(np_dtype, numpy.integer):
            # Round through the int codec via the exact Fraction hub BEFORE array construction, so
            # numpy casts already-integral Python ints (no silent truncation of fractional values).
            data = apply_leaf_codec(leaf_codec_for_name("int"), backend.fractions)
        else:
            data = _to_floats(backend.fractions)
        arr = numpy.asarray(data, dtype=np_dtype)
        instance = arr.view(cls)
        instance._backend = backend
        return instance

    def __array_ufunc__(self, ufunc: Any, method: str, *inputs: Any, **kwargs: Any) -> Any:
        # Shed the view: operate on and return base-class ndarrays.
        shed_inputs = tuple(_shed(x) for x in inputs)
        kwargs = {key: _shed(value) for key, value in kwargs.items()}
        return getattr(ufunc, method)(*shed_inputs, **kwargs)

    def __array_function__(self, func: Any, types: Any, args: Any, kwargs: Any) -> Any:
        # Shed the view for NumPy-dispatched functions (numpy.concatenate, numpy.linalg.norm, ...).
        return func(*_shed(tuple(args)), **_shed(dict(kwargs)))

    def __array_wrap__(self, obj: Any, context: Any = None, return_scalar: bool = False) -> Any:
        # Residual numpy paths that wrap results into the input's class: return base instead.
        arr = numpy.asarray(obj)
        return arr[()] if return_scalar else arr

    def __getitem__(self, key: Any) -> Any:
        # Slicing/indexing results are presentation output: base-class ndarrays (or numpy scalars).
        return self.view(numpy.ndarray)[key]

    def __reduce__(self) -> Any:
        reduced = cast(tuple[Any, tuple[Any, ...], Any], super().__reduce__())
        reconstruct, args, state = reduced
        return reconstruct, args, state + ((_BACKEND_STATE_TAG, getattr(self, "_backend", None)),)

    def __setstate__(self, state: Any) -> None:
        backend = None
        if state and isinstance(state[-1], tuple) and len(state[-1]) == 2 and state[-1][0] == _BACKEND_STATE_TAG:
            backend = state[-1][1]
            state = state[:-1]
        super().__setstate__(state)
        self.__dict__.pop("_backend", None)
        if backend is not None:
            self._backend = backend

    def __deepcopy__(self, memo: dict[int, Any] | None) -> Self:
        result = super().__deepcopy__(memo)
        backend = getattr(self, "_backend", None)
        if backend is not None:
            result._backend = copy.deepcopy(backend, memo)
        return result

    def unwrap(self) -> Any:
        """Return the original backend value, or this view when it has no backend."""
        backend = getattr(self, "_backend", None)
        if backend is None:
            return self
        return unwrap(backend)

    def unview(self) -> Any:
        """Return a base-class numpy array containing this view's data."""
        # Instances built by __new__ sit directly on their presentation array: the adopted raw
        # array or the converted base array, either way `self.base`. Derived (backend-less)
        # instances have some other base; their own data is authoritative.
        base = self.base
        if type(base) is numpy.ndarray and base.shape == self.shape and base.dtype == self.dtype:
            return base
        return self.view(numpy.ndarray)
