"""Register httk-core's vendored OPTIMADE entry-type schemas."""

from httk.core import register_entry_type_schema

register_entry_type_schema(
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    resource="httk.registry.schemas.core:references.json",
)
register_entry_type_schema(
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    resource="httk.registry.schemas.core:files.json",
)
register_entry_type_schema(
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    resource="httk.registry.schemas.core:calculations.json",
)
