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
from ._base import PluginRegistry, _same_callable_reference, resolve_callable  # noqa: F401
from .cli import (  # noqa: F401
    _CLI_NAME,
    _CLI_RESERVED,
    CLICommand,
    CLIHandler,
    _cli_commands,
    _cli_extensions,
    cli_command,
    cli_extensions,
    known_cli_commands,
    register_cli_command,
    register_cli_extension,
)
from .entries import (  # noqa: F401
    OptimadeEntryBinding,
    _entry_families,
    _entry_records,
    _optimade_entry_bindings,
    _validate_nonempty_optimade_string,
    _validate_optimade_reference,
    entry_family_info,
    entry_providers,
    entry_record_info,
    known_entry_families,
    known_entry_providers,
    known_entry_records,
    known_optimade_entry_bindings,
    optimade_entry_binding,
    register_entry_family,
    register_entry_provider,
    register_entry_record,
    register_optimade_entry_binding,
    resolve_entry_family,
    resolve_entry_record,
)
from .io import (  # noqa: F401
    _format_adapter_lock,
    _format_serializer_lock,
    _reader_key,
    _reindex_writer_format,
    _writer_for_format,
    _writer_format,
    _writer_formats,
    _writers_by_format,
    format_adapters,
    format_serializers,
    has_reader_for,
    known_extensions,
    known_filenames,
    known_format_adapters,
    known_writer_formats,
    known_writers,
    reader_filenames,
    readers,
    register_format_adapter,
    register_format_serializer,
    register_reader,
    register_writer,
    writer_filenames,
    writer_formats,
    writers,
)
from .schemas import (  # noqa: F401
    _entry_type_definitions,
    _property_definitions,
    _resource,
    known_entry_type_definitions,
    known_property_definitions,
    load_entry_type_definition,
    load_property_definition,
    register_entry_type_definition,
    register_property_definition,
)

__all__ = [
    "CLICommand",
    "CLIHandler",
    "OptimadeEntryBinding",
    "PluginRegistry",
    "cli_command",
    "cli_extensions",
    "entry_family_info",
    "entry_providers",
    "entry_record_info",
    "format_adapters",
    "format_serializers",
    "has_reader_for",
    "known_entry_families",
    "known_entry_providers",
    "known_entry_records",
    "known_entry_type_definitions",
    "known_extensions",
    "known_filenames",
    "known_format_adapters",
    "known_optimade_entry_bindings",
    "known_property_definitions",
    "known_writer_formats",
    "known_writers",
    "load_entry_type_definition",
    "load_property_definition",
    "optimade_entry_binding",
    "reader_filenames",
    "readers",
    "register_cli_command",
    "register_cli_extension",
    "register_entry_family",
    "register_entry_provider",
    "register_entry_record",
    "register_entry_type_definition",
    "register_format_adapter",
    "register_format_serializer",
    "register_optimade_entry_binding",
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
