#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Exact-rational vectors (:class:`FracVector`/:class:`FracScalar`/:class:`MutableFracVector`) and
the Vector backend/view family that lets the same tensor data be viewed as the exact
representation, plain nested sequences, or (optionally) numpy arrays.

The exact-math helpers live in :mod:`httk.core.exactmath` (type-preserving exact transcendentals
on Fraction and Decimal) and :mod:`httk.core.vectors.vectormath` (functional math wrappers).
"""

import decimal
import fractions
from typing import Any

from httk.core.views import register_coercer, view_class_coercer

from .fracvector import FracScalar, FracVector
from .leaf_codecs import LeafCodec, known_leaf_codecs, register_leaf_codec
from .mutablefracvector import MutableFracVector
from .numeric import NumericVector, numpy_available, to_numeric, to_numeric_scalar
from .scalar_like import ScalarLike
from .surdvector import SurdScalar, SurdVector
from .vector_api import VectorAPI
from .vector_backend import VectorBackend
from .vector_frac import VectorFrac
from .vector_frac_view import VectorFracView
from .vector_like import VectorLike
from .vector_native import VectorNative
from .vector_native_view import VectorNativeView
from .vector_surd import VectorSurd
from .vector_surd_view import VectorSurdView
from .vector_view import VectorView

# The numpy backend and view are optional. The numpy VIEW module subclasses numpy.ndarray at
# class-definition time, so it cannot even be imported without numpy; guard both together.
# Native is registered last since it is the broadest match; the numpy backend is registered only
# when numpy is available. Dispatch is otherwise disambiguated by an optional kind= hint.
_numpy_view_class: type[Any] | None = None
try:
    from .vector_numpy import VectorNumpy
    from .vector_numpy_view import VectorNumpyView

    _numpy_available = True
    _numpy_view_class = VectorNumpyView
    VectorBackend.backend_classes = [VectorFrac, VectorSurd, VectorNumpy, VectorNative]
except ImportError:
    _numpy_available = False
    VectorBackend.backend_classes = [VectorFrac, VectorSurd, VectorNative]


def _vector_scalar_coercer(value, target):
    """Coerce vector-family scalars and containers through the exact Fraction hub.

    ``int`` uses the exact leaf rule (integral values become ``int``, otherwise an exact
    ``Fraction``), ``float`` is the explicitly lossy float codec, ``Fraction`` is exact, and
    ``Decimal`` is exact for finite decimal expansions and context-quantized otherwise. FracScalar
    and SurdScalar preserve exact rational values. Genuine irrational surds are not approximated
    for ``int``, ``Fraction``, or ``FracScalar``; unsupported reductions return ``None``.
    Lists are mutable copies of a native view, never mutable views themselves.
    """
    from .leaf_codecs import leaf_codec_for_name

    if target is list:
        source = [value] if isinstance(value, (int, float, fractions.Fraction, decimal.Decimal)) else value
        try:
            native = VectorNativeView(source)
        except (TypeError, ValueError, OverflowError):
            return None

        def lists(node):
            return [lists(item) for item in node] if isinstance(node, tuple) else node

        return lists(native)

    scalar_targets = (int, float, fractions.Fraction, decimal.Decimal, FracScalar, SurdScalar)
    if target not in scalar_targets or isinstance(value, bool):
        return None
    if (
        not isinstance(value, (int, float, fractions.Fraction, decimal.Decimal, FracVector, SurdVector))
        and getattr(value, "dim", None) != ()
    ):
        return None
    if isinstance(value, SurdVector) and value.dim == () and not value.is_rational:
        if target is SurdScalar:
            return value._as_scalar()
        if target in (int, fractions.Fraction, FracScalar):
            return None

    try:
        from httk.core import exactmath

        fraction = exactmath._coerce(value)[0]
    except (TypeError, ValueError, OverflowError):
        return None
    if target is int:
        return leaf_codec_for_name("exact").from_fraction(fraction)
    if target is float:
        return leaf_codec_for_name("float").from_fraction(fraction)
    if target is fractions.Fraction:
        return leaf_codec_for_name("fraction").from_fraction(fraction)
    if target is decimal.Decimal:
        return leaf_codec_for_name("decimal").from_fraction(fraction)
    if target is FracScalar:
        return FracScalar(fraction)
    return SurdVector(fraction)._as_scalar()


_view_classes = [VectorFracView, VectorSurdView]
if _numpy_view_class is not None:
    _view_classes.append(_numpy_view_class)
_view_classes.append(VectorNativeView)
# The view scan serves any target some view class subclasses (tuple, numpy.ndarray, FracVector,
# ...), a superclass relation issubclass on a declared target cannot express — so it declares Any.
register_coercer(view_class_coercer(_view_classes), Any)
register_coercer(
    _vector_scalar_coercer,
    (int, float, fractions.Fraction, decimal.Decimal, FracScalar, SurdScalar, list),
)

__all__ = [
    "FracScalar",
    "FracVector",
    "LeafCodec",
    "MutableFracVector",
    "NumericVector",
    "ScalarLike",
    "SurdScalar",
    "SurdVector",
    "VectorAPI",
    "VectorBackend",
    "VectorFrac",
    "VectorFracView",
    "VectorLike",
    "VectorNative",
    "VectorNativeView",
    "VectorSurd",
    "VectorSurdView",
    "VectorView",
    "known_leaf_codecs",
    "numpy_available",
    "register_leaf_codec",
    "to_numeric",
    "to_numeric_scalar",
]

if _numpy_available:
    __all__ += ["VectorNumpy", "VectorNumpyView"]
