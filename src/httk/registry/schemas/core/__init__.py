"""Register httk-core's vendored entry-type and property schemas."""

from httk.core import register_entry_type_definition, register_property_definition

register_entry_type_definition(
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    resource="httk.registry.schemas.core:references.json",
)
register_entry_type_definition(
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    resource="httk.registry.schemas.core:files.json",
)
register_entry_type_definition(
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    resource="httk.registry.schemas.core:calculations.json",
)
register_entry_type_definition(
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/runs",
    resource="httk.registry.schemas.core:runs.json",
)
register_entry_type_definition(
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/records",
    resource="httk.registry.schemas.core:records.json",
)

register_property_definition(
    definition_id="https://schemas.httk.org/defs/v0.1/properties/core/total_energy",
    resource="httk.registry.schemas.core:total_energy.json",
)
register_property_definition(
    definition_id="https://schemas.httk.org/defs/v0.1/properties/core/average_total_energy",
    resource="httk.registry.schemas.core:average_total_energy.json",
)
