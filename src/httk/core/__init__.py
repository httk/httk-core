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

from . import _discover, exactmath
from .cli_context import CLIContext
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
from .ed25519 import (
    derive_ed25519_public_key,
    ed25519_backend_available,
    ed25519_generate_seed,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
    generate_ed25519_seed,
    sign_ed25519,
    verify_ed25519,
)
from .entry_provider import EntryProvider, RelatedEntry
from .entry_types import Calculation, File, Reference
from .loading import load
from .optimade_filter import (
    FilterAst,
    ParserError,
    ParserSyntaxError,
    parse_optimade_filter,
)
from .precision import combined_precision, decimal_precision
from .property_definitions import (
    EntryTypeDefinition,
    PropertyDefinition,
    known_definition_prefixes,
    load_entry_type_definition,
    register_definition_prefix,
    standard_entry_type,
)
from .register import (
    known_cli_commands,
    known_entry_providers,
    known_format_adapters,
    register_cli_command,
    register_entry_provider,
    register_format_adapter,
)
from .storage_markers import (
    STORAGE_INFO_ATTRIBUTE,
    DedupPolicy,
    Indexed,
    Related,
    RelationshipLink,
    Shape,
    Skip,
    StorageInfo,
    Unique,
    stored_property,
)
from .vectors import (
    FracScalar,
    FracVector,
    LeafCodec,
    MutableFracVector,
    NumericVector,
    ScalarLike,
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
    known_leaf_codecs,
    numpy_available,
    register_leaf_codec,
    to_numeric,
    to_numeric_scalar,
)
from .vectors import _numpy_available as _vectors_numpy_available
from .views import Backend, View, coerce, register_coercer, unwrap

if _vectors_numpy_available:
    from .vectors import VectorNumpy, VectorNumpyView

_discover.discover_and_register()


def _discover_modules():
    prefix = httk.__name__ + "."
    names = [m.name for m in pkgutil.iter_modules(httk.__path__, prefix) if m.ispkg]
    return names


subpackages = _discover_modules()

__all__ = [
    "STORAGE_INFO_ATTRIBUTE",
    "Backend",
    "BytestreamBackend",
    "BytestreamBytes",
    "BytestreamBytesView",
    "BytestreamCommon",
    "BytestreamFile",
    "BytestreamFileView",
    "BytestreamFilename",
    "BytestreamFilenameView",
    "BytestreamLike",
    "BytestreamRequest",
    "BytestreamRequestView",
    "BytestreamURL",
    "BytestreamURLView",
    "BytestreamView",
    "CLIContext",
    "Calculation",
    "CompressionCodec",
    "DataLoader",
    "DataRecord",
    "DatasetMeta",
    "DecodeObjectCallback",
    "DedupPolicy",
    "EntryProvider",
    "EntryTypeDefinition",
    "File",
    "FilterAst",
    "FracScalar",
    "FracVector",
    "Indexed",
    "LeafCodec",
    "MutableFracVector",
    "NumericVector",
    "ParserError",
    "ParserSyntaxError",
    "PropertyDefinition",
    "Reference",
    "Related",
    "RelatedEntry",
    "RelationshipLink",
    "ScalarLike",
    "Shape",
    "Skip",
    "StorageInfo",
    "SurdScalar",
    "SurdVector",
    "TextstreamBackend",
    "TextstreamCommon",
    "TextstreamFile",
    "TextstreamFileView",
    "TextstreamFilename",
    "TextstreamFilenameView",
    "TextstreamLike",
    "TextstreamRequest",
    "TextstreamRequestView",
    "TextstreamString",
    "TextstreamStringView",
    "TextstreamURL",
    "TextstreamURLView",
    "TextstreamView",
    "Unique",
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
    "View",
    "coerce",
    "combined_precision",
    "decimal_precision",
    "derive_ed25519_public_key",
    "ed25519_backend_available",
    "ed25519_generate_seed",
    "ed25519_public_key",
    "ed25519_sign",
    "ed25519_verify",
    "exactmath",
    "generate_ed25519_seed",
    "known_cli_commands",
    "known_compressions",
    "known_definition_prefixes",
    "known_entry_providers",
    "known_format_adapters",
    "known_leaf_codecs",
    "load",
    "load_entry_type_definition",
    "numpy_available",
    "parse_optimade_filter",
    "register_cli_command",
    "register_coercer",
    "register_compression",
    "register_definition_prefix",
    "register_entry_provider",
    "register_format_adapter",
    "register_leaf_codec",
    "sign_ed25519",
    "standard_entry_type",
    "stored_property",
    "subpackages",
    "to_numeric",
    "to_numeric_scalar",
    "unwrap",
    "verify_ed25519",
]

if _vectors_numpy_available:
    __all__ += ["VectorNumpy", "VectorNumpyView"]
