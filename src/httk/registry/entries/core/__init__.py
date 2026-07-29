"""Register classes from ``httk.core.entry_types`` as lazy registry pointers."""

from httk.core import register_entry_record

register_entry_record(
    name="core-reference",
    record="httk.core.entry_types:Reference",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
)
register_entry_record(
    name="core-file",
    record="httk.core.entry_types:File",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
)
register_entry_record(
    name="core-calculation",
    record="httk.core.entry_types:Calculation",
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
)
