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
from .dataset_loader import DatasetLoader, DatasetMeta, DatasetRecord
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
    DatastreamLike,
    DatastreamURL,
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
from .ed25519 import ed25519_backend_available, ed25519_generate_seed, ed25519_public_key, ed25519_sign, ed25519_verify
from .entry_provider import EntryProvider, RelatedEntry
from .entry_types import Calculation, File, Reference
from .fetching import fetch
from .identity import (
    StorageProjectionCycleError,
    canonical_form,
    content_id,
    project_storage_record,
    register_canonical_encoder,
    resolve_storage_record,
)
from .loading import has_loader_for, load, load_source
from .optimade_entries import (
    CalculationView,
    FileView,
    IncompleteOptimadeResourceError,
    OptimadeCalculation,
    OptimadeEntryBackend,
    OptimadeEntryView,
    OptimadeFile,
    OptimadeReference,
    ReferenceView,
    decode_optimade_value,
)
from .optimade_filter import (
    FilterAst,
    ParserError,
    ParserSyntaxError,
    parse_optimade_filter,
)
from .optimade_resources import (
    OptimadeDocument,
    OptimadeResource,
    OptimadeSchemaSnapshot,
    is_optimade_entry_url,
    optimade_document_root,
    redact_optimade_url,
)
from .precision import combined_precision, decimal_precision
from .property_definitions import (
    EntryTypeDefinition,
    PropertyDefinition,
    known_definition_prefixes,
    register_definition_prefix,
    standard_entry_type,
)
from .register import (
    OptimadeEntryBinding,
    entry_family_info,
    entry_record_info,
    known_entry_families,
    known_entry_providers,
    known_entry_records,
    known_entry_type_definitions,
    known_optimade_entry_bindings,
    load_entry_type_definition,
    load_property_definition,
    optimade_entry_binding,
    register_cli_command,
    register_entry_family,
    register_entry_provider,
    register_entry_record,
    register_entry_type_definition,
    register_format_adapter,
    register_optimade_entry_binding,
    register_property_definition,
    resolve_entry_family,
    resolve_entry_record,
)
from .storage_markers import (
    STORAGE_INFO_ATTRIBUTE,
    DedupPolicy,
    IdentitySkip,
    Indexed,
    Related,
    RelationshipLink,
    Shape,
    Skip,
    StorageInfo,
    Unique,
    stored_property,
)
from .stored_properties import (
    QueryContext,
    QueryExpression,
    QueryField,
    QueryLiteralError,
    QueryScope,
    QueryValue,
    StoredPropertyProjection,
    stored_property_projections,
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
    known_leaf_codecs,
    numpy_available,
    register_leaf_codec,
    to_numeric,
    to_numeric_scalar,
)
from .vectors import _numpy_available as _vectors_numpy_available
from .views import Backend, View, coerce, unwrap

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
    "CalculationView",
    "CompressionCodec",
    "DatasetLoader",
    "DatasetMeta",
    "DatasetRecord",
    "DatastreamLike",
    "DatastreamURL",
    "DedupPolicy",
    "EntryProvider",
    "EntryTypeDefinition",
    "File",
    "FileView",
    "FilterAst",
    "FracScalar",
    "FracVector",
    "IdentitySkip",
    "IncompleteOptimadeResourceError",
    "Indexed",
    "LeafCodec",
    "MutableFracVector",
    "NumericVector",
    "OptimadeCalculation",
    "OptimadeDocument",
    "OptimadeEntryBackend",
    "OptimadeEntryBinding",
    "OptimadeEntryView",
    "OptimadeFile",
    "OptimadeReference",
    "OptimadeResource",
    "OptimadeSchemaSnapshot",
    "ParserError",
    "ParserSyntaxError",
    "PropertyDefinition",
    "QueryContext",
    "QueryExpression",
    "QueryField",
    "QueryLiteralError",
    "QueryScope",
    "QueryValue",
    "Reference",
    "ReferenceView",
    "Related",
    "RelatedEntry",
    "RelationshipLink",
    "ScalarLike",
    "Shape",
    "Skip",
    "StorageInfo",
    "StorageProjectionCycleError",
    "StoredPropertyProjection",
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
    "View",
    "canonical_form",
    "coerce",
    "combined_precision",
    "content_id",
    "decimal_precision",
    "decode_optimade_value",
    "ed25519_backend_available",
    "ed25519_generate_seed",
    "ed25519_public_key",
    "ed25519_sign",
    "ed25519_verify",
    "entry_family_info",
    "entry_record_info",
    "exactmath",
    "fetch",
    "has_loader_for",
    "is_optimade_entry_url",
    "known_compressions",
    "known_definition_prefixes",
    "known_entry_families",
    "known_entry_providers",
    "known_entry_records",
    "known_entry_type_definitions",
    "known_leaf_codecs",
    "known_optimade_entry_bindings",
    "load",
    "load_entry_type_definition",
    "load_property_definition",
    "load_source",
    "numpy_available",
    "optimade_document_root",
    "optimade_entry_binding",
    "parse_optimade_filter",
    "project_storage_record",
    "redact_optimade_url",
    "register_canonical_encoder",
    "register_cli_command",
    "register_compression",
    "register_definition_prefix",
    "register_entry_family",
    "register_entry_provider",
    "register_entry_record",
    "register_entry_type_definition",
    "register_format_adapter",
    "register_leaf_codec",
    "register_optimade_entry_binding",
    "register_property_definition",
    "resolve_entry_family",
    "resolve_entry_record",
    "resolve_storage_record",
    "standard_entry_type",
    "stored_property",
    "stored_property_projections",
    "subpackages",
    "to_numeric",
    "to_numeric_scalar",
    "unwrap",
]

if _vectors_numpy_available:
    __all__ += ["VectorNumpy", "VectorNumpyView"]
