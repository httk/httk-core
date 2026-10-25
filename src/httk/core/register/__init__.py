"""Backward-compatible exports for registry implementations split by type."""

#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation; either version 3 of the
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

# The re-exports resolve lazily (PEP 562 ``__getattr__``) so that registering a CLI command does not import
# the I/O registry and its datastream dependencies. The static view is the ``__init__.pyi`` stub beside this file.
# pyright: reportUnsupportedDunderAll=false

__all__ = [
    "CLICommand",
    "CLIHandler",
    "CodeSupport",
    "CollectorSupport",
    "OptimadeEntryBinding",
    "PluginRegistry",
    "cli_command",
    "code_support",
    "collector_support",
    "entry_family_info",
    "entry_providers",
    "entry_record_info",
    "format_adapters",
    "format_serializers",
    "has_reader_for",
    "known_codes",
    "known_collectors",
    "known_entry_families",
    "known_entry_providers",
    "known_entry_records",
    "known_entry_type_definitions",
    "known_extensions",
    "known_filenames",
    "known_format_adapters",
    "known_optimade_entry_bindings",
    "known_project_member_kinds",
    "known_property_definitions",
    "known_reader_formats",
    "known_writer_formats",
    "known_writers",
    "load_entry_type_definition",
    "load_property_definition",
    "optimade_entry_binding",
    "project_member_handler",
    "reader_filenames",
    "reader_format_for",
    "reader_formats",
    "readers",
    "register_cli_command",
    "register_code",
    "register_collector",
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
    "resolve_callable",
    "resolve_entry_family",
    "resolve_entry_record",
    "writer_filenames",
    "writer_formats",
    "writers",
]

_LAZY_EXPORTS = {
    "PluginRegistry": "_base",
    "_same_callable_reference": "_base",
    "resolve_callable": "_base",
    "_CLI_NAME": "cli",
    "_CLI_RESERVED": "cli",
    "CLICommand": "cli",
    "CLIHandler": "cli",
    "_cli_commands": "cli",
    "cli_command": "cli",
    "known_cli_commands": "cli",
    "register_cli_command": "cli",
    "CodeSupport": "codes",
    "CollectorSupport": "codes",
    "code_support": "codes",
    "collector_support": "codes",
    "known_codes": "codes",
    "known_collectors": "codes",
    "register_code": "codes",
    "register_collector": "codes",
    "OptimadeEntryBinding": "entries",
    "_entry_families": "entries",
    "_entry_records": "entries",
    "_optimade_entry_bindings": "entries",
    "_validate_nonempty_optimade_string": "entries",
    "_validate_optimade_reference": "entries",
    "entry_family_info": "entries",
    "entry_providers": "entries",
    "entry_record_info": "entries",
    "known_entry_families": "entries",
    "known_entry_providers": "entries",
    "known_entry_records": "entries",
    "known_optimade_entry_bindings": "entries",
    "optimade_entry_binding": "entries",
    "register_entry_family": "entries",
    "register_entry_provider": "entries",
    "register_entry_record": "entries",
    "register_optimade_entry_binding": "entries",
    "resolve_entry_family": "entries",
    "resolve_entry_record": "entries",
    "_format_adapter_lock": "io",
    "_format_serializer_lock": "io",
    "_reader_key": "io",
    "_reindex_writer_format": "io",
    "_writer_for_format": "io",
    "_writer_format": "io",
    "_writer_formats": "io",
    "_writers_by_format": "io",
    "format_adapters": "io",
    "format_serializers": "io",
    "has_reader_for": "io",
    "known_extensions": "io",
    "known_filenames": "io",
    "known_format_adapters": "io",
    "known_reader_formats": "io",
    "known_writer_formats": "io",
    "known_writers": "io",
    "reader_filenames": "io",
    "reader_format_for": "io",
    "reader_formats": "io",
    "readers": "io",
    "register_format_adapter": "io",
    "register_format_serializer": "io",
    "register_reader": "io",
    "register_writer": "io",
    "writer_filenames": "io",
    "writer_formats": "io",
    "writers": "io",
    "known_project_member_kinds": "members",
    "project_member_handler": "members",
    "project_member_kinds": "members",
    "register_project_member_kind": "members",
    "_entry_type_definitions": "schemas",
    "_property_definitions": "schemas",
    "_resource": "schemas",
    "known_entry_type_definitions": "schemas",
    "known_property_definitions": "schemas",
    "load_entry_type_definition": "schemas",
    "load_property_definition": "schemas",
    "register_entry_type_definition": "schemas",
    "register_property_definition": "schemas",
}


def __getattr__(name: str) -> Any:
    """Import a root re-export from its submodule on first access.

    :param name: The module attribute to resolve.
    :return: The requested re-export.
    :raises AttributeError: If ``name`` is not a root re-export.
    """
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
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
