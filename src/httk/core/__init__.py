"""Public core APIs for loading, reporting, project anchors, and registration.

Importing this package discovers installed capability modules and exposes
their registered readers, writers, adapters, and related public APIs.

The deliberate public surface is defined by ``__all__``.
"""

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

from . import exactmath  # noqa: F401 - intentional module-level import for ``from httk.core import exactmath``
from ._discover import discover_and_register as _discover_and_register
from ._sentinel import MISSING, MissingType
from .citations import credits, register_citation
from .cli import CLIContext
from .data_records import DataRecord, DataRecordEntry
from .dataset_loader import DatasetLoader, DatasetLoaderRecord, DatasetMeta
from .datasets import Dataset, DatasetDistribution, DatasetRecord
from .datastream import (
    BytestreamFileView,
    BytestreamLike,
    BytestreamURLView,
    CompressionCodec,
    DatastreamLike,
    DatastreamURL,
    TextstreamFileView,
    TextstreamLike,
    TextstreamURLView,
    known_compressions,
    register_compression,
)
from .entry_ids import (
    ALTERNATIVE_ID_PATTERN,
    ALTERNATIVE_KIND_PATTERN,
    ENTRY_ID_PATTERN,
    IMMUTABLE_ID_PATTERN,
    check_entry_id,
    check_immutable_id,
    format_alternative_id,
    format_entry_id,
    format_immutable_id,
    is_url_safe_id,
    parse_alternative_id,
    parse_entry_id,
    parse_immutable_id,
)
from .entry_provider import EntryProvider, RelatedEntry
from .entry_types import Calculation, File, Reference
from .fetching import fetch
from .files import FileEntry, FileRecord
from .loading import has_reader_for, load, load_many, load_source
from .precision import combined_precision, decimal_precision
from .property_definitions import (
    EntryTypeDefinition,
    PropertyDefinition,
    known_definition_prefixes,
    register_definition_prefix,
    standard_entry_type,
)
from .provenance import ProductLink, Run, RunEdge, RunEntry
from .register.cli import register_cli_command
from .register.entries import (
    known_entry_providers,
    register_entry_family,
    register_entry_provider,
    register_entry_record,
    register_optimade_entry_binding,
)
from .register.io import (
    register_format_adapter,
    register_format_serializer,
    register_reader,
    register_writer,
)
from .register.members import (
    known_project_member_kinds,
    project_member_handler,
    register_project_member_kind,
)
from .register.schemas import (
    load_entry_type_definition,
    load_property_definition,
    register_entry_type_definition,
    register_property_definition,
)
from .saving import has_writer_for, save
from .services import Service, ServiceRecord
from .storage.identity import content_id
from .storage.markers import (
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
from .vectors import (
    FracScalar,
    FracVector,
    MutableFracVector,
    NumericVector,
    ScalarLike,
    SurdScalar,
    SurdVector,
    VectorLike,
    numpy_available,
    to_numeric,
    to_numeric_scalar,
)
from .views import Backend, View, coerce, coerce_view, unview, unwrap

_discover_and_register()

__all__ = [
    "ALTERNATIVE_ID_PATTERN",
    "ALTERNATIVE_KIND_PATTERN",
    "ENTRY_ID_PATTERN",
    "IMMUTABLE_ID_PATTERN",
    "MISSING",
    "Backend",
    "BytestreamFileView",
    "BytestreamLike",
    "BytestreamURLView",
    "CLIContext",
    "Calculation",
    "CompressionCodec",
    "DataRecord",
    "DataRecordEntry",
    "Dataset",
    "DatasetDistribution",
    "DatasetLoader",
    "DatasetLoaderRecord",
    "DatasetMeta",
    "DatasetRecord",
    "DatastreamLike",
    "DatastreamURL",
    "EntryProvider",
    "EntryTypeDefinition",
    "File",
    "FileEntry",
    "FileRecord",
    "FracScalar",
    "FracVector",
    "IdentitySkip",
    "Indexed",
    "MissingType",
    "MutableFracVector",
    "NumericVector",
    "ProductLink",
    "PropertyDefinition",
    "Reference",
    "Related",
    "RelatedEntry",
    "RelationshipLink",
    "Run",
    "RunEdge",
    "RunEntry",
    "ScalarLike",
    "Service",
    "ServiceRecord",
    "Shape",
    "Skip",
    "StorageInfo",
    "SurdScalar",
    "SurdVector",
    "TextstreamFileView",
    "TextstreamLike",
    "TextstreamURLView",
    "Unique",
    "VectorLike",
    "View",
    "check_entry_id",
    "check_immutable_id",
    "coerce",
    "coerce_view",
    "combined_precision",
    "content_id",
    "credits",
    "decimal_precision",
    "fetch",
    "format_alternative_id",
    "format_entry_id",
    "format_immutable_id",
    "has_reader_for",
    "has_writer_for",
    "is_url_safe_id",
    "known_compressions",
    "known_definition_prefixes",
    "known_entry_providers",
    "known_project_member_kinds",
    "load",
    "load_entry_type_definition",
    "load_many",
    "load_property_definition",
    "load_source",
    "numpy_available",
    "parse_alternative_id",
    "parse_entry_id",
    "parse_immutable_id",
    "project_member_handler",
    "register_citation",
    "register_cli_command",
    "register_compression",
    "register_definition_prefix",
    "register_entry_family",
    "register_entry_provider",
    "register_entry_record",
    "register_entry_type_definition",
    "register_format_adapter",
    "register_format_serializer",
    "register_optimade_entry_binding",
    "register_project_member_kind",
    "register_property_definition",
    "register_reader",
    "register_writer",
    "save",
    "standard_entry_type",
    "stored_property",
    "to_numeric",
    "to_numeric_scalar",
    "unview",
    "unwrap",
]
