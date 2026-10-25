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

import importlib
from typing import Any

from ._discover import discover_and_register as _discover_and_register

# The root re-exports resolve lazily (PEP 562 ``__getattr__``, as in ``httk.workflow``) so that
# ``import httk.core.cli``, and therefore every ``httk`` command start, stays free of numpy and of the
# ~130 submodules behind the public surface. Registration discovery stays eager (end of module). The static view, for
# type checkers and the API reference, is the ``__init__.pyi`` stub beside this file.
# pyright: reportUnsupportedDunderAll=false

__all__ = [
    "ALTERNATIVE_ID_PATTERN",
    "ALTERNATIVE_KIND_PATTERN",
    "ENTRY_ID_PATTERN",
    "IMMUTABLE_ID_PATTERN",
    "MISSING",
    "AverageTotalEnergyRecord",
    "Backend",
    "BytestreamFileView",
    "BytestreamLike",
    "BytestreamURLView",
    "CLIContext",
    "Calculation",
    "CompressionCodec",
    "DataEntryRecord",
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
    "DerivedDataRecord",
    "EntryProvider",
    "EntryRecord",
    "EntryTypeDefinition",
    "File",
    "FileEntry",
    "FileRecord",
    "FracScalar",
    "FracVector",
    "IdentitySkip",
    "IdentitySkipWhenNone",
    "Indexed",
    "KeepStored",
    "MemberLayout",
    "MissingType",
    "MutableFracVector",
    "NumericVector",
    "PersonRecord",
    "ProductLink",
    "Property",
    "PropertyDefinition",
    "Reference",
    "ReferenceEntry",
    "ReferenceRecord",
    "Related",
    "RelatedEntry",
    "Run",
    "RunEdge",
    "RunEntry",
    "ScalarLike",
    "Service",
    "ServiceRecord",
    "Shape",
    "Skip",
    "StorageInfo",
    "StrongLink",
    "SurdScalar",
    "SurdVector",
    "TextstreamFileView",
    "TextstreamLike",
    "TextstreamURLView",
    "TotalEnergyRecord",
    "TypedRecord",
    "TypedRecordSpec",
    "Unique",
    "VectorLike",
    "View",
    "WeakLink",
    "apply_definition_prefix",
    "check_entry_id",
    "check_immutable_id",
    "coerce",
    "coerce_view",
    "combined_precision",
    "content_id",
    "credits",
    "decimal_precision",
    "entry_record",
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
    "member_layout",
    "numpy_available",
    "parse_alternative_id",
    "parse_entry_id",
    "parse_immutable_id",
    "project_member_handler",
    "reader_format_for",
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

_LAZY_EXPORTS = {
    "MISSING": "_sentinel",
    "MissingType": "_sentinel",
    "credits": "citations",
    "register_citation": "citations",
    "CLIContext": "cli",
    "AverageTotalEnergyRecord": "data_records",
    "DataRecord": "data_records",
    "DataRecordEntry": "data_records",
    "DerivedDataRecord": "data_records",
    "TotalEnergyRecord": "data_records",
    "DatasetLoader": "dataset_loader",
    "DatasetLoaderRecord": "dataset_loader",
    "DatasetMeta": "dataset_loader",
    "Dataset": "datasets",
    "DatasetDistribution": "datasets",
    "DatasetRecord": "datasets",
    "BytestreamFileView": "datastream",
    "BytestreamLike": "datastream",
    "BytestreamURLView": "datastream",
    "CompressionCodec": "datastream",
    "DatastreamLike": "datastream",
    "DatastreamURL": "datastream",
    "TextstreamFileView": "datastream",
    "TextstreamLike": "datastream",
    "TextstreamURLView": "datastream",
    "known_compressions": "datastream",
    "register_compression": "datastream",
    "ALTERNATIVE_ID_PATTERN": "entry_ids",
    "ALTERNATIVE_KIND_PATTERN": "entry_ids",
    "ENTRY_ID_PATTERN": "entry_ids",
    "IMMUTABLE_ID_PATTERN": "entry_ids",
    "check_entry_id": "entry_ids",
    "check_immutable_id": "entry_ids",
    "format_alternative_id": "entry_ids",
    "format_entry_id": "entry_ids",
    "format_immutable_id": "entry_ids",
    "is_url_safe_id": "entry_ids",
    "parse_alternative_id": "entry_ids",
    "parse_entry_id": "entry_ids",
    "parse_immutable_id": "entry_ids",
    "EntryProvider": "entry_provider",
    "RelatedEntry": "entry_provider",
    "DataEntryRecord": "entry_records",
    "EntryRecord": "entry_records",
    "Property": "entry_records",
    "entry_record": "entry_records",
    "Calculation": "entry_types",
    "File": "entry_types",
    "Reference": "entry_types",
    "fetch": "fetching",
    "FileEntry": "files",
    "FileRecord": "files",
    "has_reader_for": "loading",
    "load": "loading",
    "load_many": "loading",
    "load_source": "loading",
    "reader_format_for": "loading",
    "combined_precision": "precision",
    "decimal_precision": "precision",
    "EntryTypeDefinition": "property_definitions",
    "PropertyDefinition": "property_definitions",
    "apply_definition_prefix": "property_definitions",
    "known_definition_prefixes": "property_definitions",
    "register_definition_prefix": "property_definitions",
    "standard_entry_type": "property_definitions",
    "ProductLink": "provenance",
    "Run": "provenance",
    "RunEdge": "provenance",
    "RunEntry": "provenance",
    "PersonRecord": "references",
    "ReferenceEntry": "references",
    "ReferenceRecord": "references",
    "register_cli_command": "register.cli",
    "known_entry_providers": "register.entries",
    "register_entry_family": "register.entries",
    "register_entry_provider": "register.entries",
    "register_entry_record": "register.entries",
    "register_optimade_entry_binding": "register.entries",
    "register_format_adapter": "register.io",
    "register_format_serializer": "register.io",
    "register_reader": "register.io",
    "register_writer": "register.io",
    "known_project_member_kinds": "register.members",
    "project_member_handler": "register.members",
    "register_project_member_kind": "register.members",
    "load_entry_type_definition": "register.schemas",
    "load_property_definition": "register.schemas",
    "register_entry_type_definition": "register.schemas",
    "register_property_definition": "register.schemas",
    "has_writer_for": "saving",
    "save": "saving",
    "Service": "services",
    "ServiceRecord": "services",
    "content_id": "storage.identity",
    "IdentitySkip": "storage.markers",
    "IdentitySkipWhenNone": "storage.markers",
    "Indexed": "storage.markers",
    "KeepStored": "storage.markers",
    "Related": "storage.markers",
    "Shape": "storage.markers",
    "Skip": "storage.markers",
    "StorageInfo": "storage.markers",
    "StrongLink": "storage.markers",
    "Unique": "storage.markers",
    "WeakLink": "storage.markers",
    "stored_property": "storage.markers",
    "MemberLayout": "typed_records",
    "TypedRecord": "typed_records",
    "TypedRecordSpec": "typed_records",
    "member_layout": "typed_records",
    "FracScalar": "vectors",
    "FracVector": "vectors",
    "MutableFracVector": "vectors",
    "NumericVector": "vectors",
    "ScalarLike": "vectors",
    "SurdScalar": "vectors",
    "SurdVector": "vectors",
    "VectorLike": "vectors",
    "numpy_available": "vectors",
    "to_numeric": "vectors",
    "to_numeric_scalar": "vectors",
    "Backend": "views",
    "View": "views",
    "coerce": "views",
    "coerce_view": "views",
    "unview": "views",
    "unwrap": "views",
}

# Submodules the root has always bound as attributes; resolved lazily like the re-exports.
_LAZY_MODULES = frozenset({"exactmath"})


def __getattr__(name: str) -> Any:
    """Import a root re-export, or a lazily bound submodule, on first access.

    :param name: The module attribute to resolve.
    :return: The requested re-export or submodule.
    :raises AttributeError: If ``name`` is neither.
    """
    if name in _LAZY_MODULES:
        return importlib.import_module(f".{name}", __name__)
    submodule = _LAZY_EXPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{submodule}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List the module attributes, including the not yet resolved re-exports.

    :return: The sorted attribute names.
    """
    return sorted(set(globals()) | set(_LAZY_EXPORTS) | _LAZY_MODULES)


_discover_and_register()
