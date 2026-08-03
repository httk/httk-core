"""Register core entry records and typed OPTIMADE bindings lazily."""

from httk.core import register_entry_record, register_optimade_entry_binding

register_entry_record(
    name="core-reference",
    record="httk.core.entry_types:Reference",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
)

register_optimade_entry_binding(
    name="core-reference",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    backend="httk.core.optimade.entries:OptimadeReference",
    view="httk.core.optimade.entries:ReferenceView",
    query_fields=None,
)
register_optimade_entry_binding(
    name="core-file",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    backend="httk.core.optimade.entries:OptimadeFile",
    view="httk.core.optimade.entries:FileView",
    query_fields=None,
)
register_optimade_entry_binding(
    name="core-calculation",
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    backend="httk.core.optimade.entries:OptimadeCalculation",
    view="httk.core.optimade.entries:CalculationView",
    query_fields=None,
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
