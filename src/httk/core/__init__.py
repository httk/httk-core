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

import pkgutil

import httk

from . import _discover
from .dataloader import DataLoader, DataRecord, DatasetMeta, DecodeObjectCallback
from .datastream import (
    BytestreamBackend,
    BytestreamBytes,
    BytestreamBytesView,
    BytestreamCommon,
    BytestreamFile,
    BytestreamFilename,
    BytestreamFilenameView,
    BytestreamFileView,
    BytestreamLike,
    BytestreamRequest,
    BytestreamRequestView,
    BytestreamURL,
    BytestreamURLView,
    BytestreamView,
    CompressionCodec,
    TextstreamBackend,
    TextstreamCommon,
    TextstreamFile,
    TextstreamFilename,
    TextstreamFilenameView,
    TextstreamFileView,
    TextstreamLike,
    TextstreamRequest,
    TextstreamRequestView,
    TextstreamString,
    TextstreamStringView,
    TextstreamURL,
    TextstreamURLView,
    TextstreamView,
    known_compressions,
    register_compression,
)
from .entry_provider import EntryProvider
from .loading import load
from .register import known_entry_providers, register_entry_provider
from .vectors import (
    FracScalar,
    FracVector,
    LeafCodec,
    MutableFracVector,
    NumericVector,
    SurdScalar,
    SurdVector,
    VectorAPI,
    VectorBackend,
    VectorFrac,
    VectorFracView,
    VectorLike,
    VectorNative,
    VectorNativeView,
    VectorSurd,
    VectorSurdView,
    VectorView,
)
from .vectors import _numpy_available as _vectors_numpy_available
from .vectors import (
    known_leaf_codecs,
    numpy_available,
    register_leaf_codec,
    to_numeric,
    to_numeric_scalar,
)
from .views import Backend, View, unwrap

if _vectors_numpy_available:
    from .vectors import VectorNumpy, VectorNumpyView

_discover.discover_and_register()


def _discover_modules():
    prefix = httk.__name__ + "."
    names = [m.name for m in pkgutil.iter_modules(httk.__path__, prefix) if m.ispkg]
    return names


subpackages = _discover_modules()

__all__ = [
    "load",
    "subpackages",
    "EntryProvider",
    "register_entry_provider",
    "known_entry_providers",
    "DataLoader",
    "DataRecord",
    "DatasetMeta",
    "DecodeObjectCallback",
    "Backend",
    "View",
    "unwrap",
    "BytestreamView",
    "BytestreamFileView",
    "BytestreamFilenameView",
    "BytestreamBytesView",
    "BytestreamRequestView",
    "BytestreamURLView",
    "BytestreamBackend",
    "BytestreamCommon",
    "BytestreamFile",
    "BytestreamFilename",
    "BytestreamBytes",
    "BytestreamRequest",
    "BytestreamURL",
    "BytestreamLike",
    "TextstreamView",
    "TextstreamFileView",
    "TextstreamFilenameView",
    "TextstreamStringView",
    "TextstreamRequestView",
    "TextstreamURLView",
    "TextstreamBackend",
    "TextstreamCommon",
    "TextstreamFile",
    "TextstreamFilename",
    "TextstreamString",
    "TextstreamRequest",
    "TextstreamURL",
    "TextstreamLike",
    "CompressionCodec",
    "register_compression",
    "known_compressions",
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

if _vectors_numpy_available:
    __all__ += ["VectorNumpy", "VectorNumpyView"]
