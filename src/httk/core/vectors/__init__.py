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

The exact-math helpers live in the submodules :mod:`httk.core.vectors.exactmath` (type-preserving
exact transcendentals on Fraction and Decimal) and :mod:`httk.core.vectors.vectormath` (functional
math wrappers).
"""

from .fracvector import FracScalar, FracVector
from .leaf_codecs import LeafCodec, known_leaf_codecs, register_leaf_codec
from .mutablefracvector import MutableFracVector
from .numeric import NumericVector, numpy_available, to_numeric, to_numeric_scalar
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
try:
    from .vector_numpy import VectorNumpy
    from .vector_numpy_view import VectorNumpyView

    _numpy_available = True
    VectorBackend.backend_classes = [VectorFrac, VectorSurd, VectorNumpy, VectorNative]
except ImportError:
    _numpy_available = False
    VectorBackend.backend_classes = [VectorFrac, VectorSurd, VectorNative]

__all__ = [
    "FracVector",
    "FracScalar",
    "MutableFracVector",
    "SurdVector",
    "SurdScalar",
    "LeafCodec",
    "register_leaf_codec",
    "known_leaf_codecs",
    "VectorAPI",
    "VectorBackend",
    "VectorView",
    "VectorFrac",
    "VectorNative",
    "VectorSurd",
    "VectorFracView",
    "VectorNativeView",
    "VectorSurdView",
    "VectorLike",
    "NumericVector",
    "to_numeric",
    "to_numeric_scalar",
    "numpy_available",
]

if _numpy_available:
    __all__ += ["VectorNumpy", "VectorNumpyView"]
