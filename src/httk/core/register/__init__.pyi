"""Backward-compatible exports for registry implementations split by type."""

from ._base import PluginRegistry, resolve_callable
from ._base import _same_callable_reference as _same_callable_reference
from .cli import _CLI_NAME as _CLI_NAME
from .cli import _CLI_RESERVED as _CLI_RESERVED
from .cli import CLICommand, CLIHandler, cli_command, register_cli_command
from .cli import _cli_commands as _cli_commands
from .cli import known_cli_commands as known_cli_commands
from .codes import (
    CodeSupport,
    CollectorSupport,
    code_support,
    collector_support,
    known_codes,
    known_collectors,
    register_code,
    register_collector,
)
from .entries import (
    OptimadeEntryBinding,
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
from .entries import _entry_families as _entry_families
from .entries import _entry_records as _entry_records
from .entries import _optimade_entry_bindings as _optimade_entry_bindings
from .entries import _validate_nonempty_optimade_string as _validate_nonempty_optimade_string
from .entries import _validate_optimade_reference as _validate_optimade_reference
from .io import _format_adapter_lock as _format_adapter_lock
from .io import _format_serializer_lock as _format_serializer_lock
from .io import _reader_key as _reader_key
from .io import _reindex_writer_format as _reindex_writer_format
from .io import _writer_for_format as _writer_for_format
from .io import _writer_format as _writer_format
from .io import _writer_formats as _writer_formats
from .io import _writers_by_format as _writers_by_format
from .io import (
    format_adapters,
    format_serializers,
    has_reader_for,
    known_extensions,
    known_filenames,
    known_format_adapters,
    known_reader_formats,
    known_writer_formats,
    known_writers,
    reader_filenames,
    reader_format_for,
    reader_formats,
    readers,
    register_format_adapter,
    register_format_serializer,
    register_reader,
    register_writer,
    writer_filenames,
    writer_formats,
    writers,
)
from .members import known_project_member_kinds, project_member_handler, register_project_member_kind
from .members import project_member_kinds as project_member_kinds
from .schemas import _entry_type_definitions as _entry_type_definitions
from .schemas import _property_definitions as _property_definitions
from .schemas import _resource as _resource
from .schemas import (
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
