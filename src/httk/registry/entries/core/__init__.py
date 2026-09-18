"""Register core entry families, records, and typed OPTIMADE bindings lazily."""

from httk.core import register_entry_family, register_entry_record, register_optimade_entry_binding

register_entry_family(
    name="runs",
    family="httk.core.provenance:RunEntry",
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/runs",
)
register_entry_family(
    name="records",
    family="httk.core.data_records:DataRecordEntry",
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/records",
)
register_entry_family(
    name="files",
    family="httk.core.files:FileEntry",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
)
register_entry_record(
    name="core-run",
    record="httk.core.provenance:Run",
    family="runs",
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/runs",
)
register_entry_record(
    name="core-data-record",
    record="httk.core.data_records:DataRecord",
    family="records",
    definition_id="https://schemas.httk.org/defs/v0.1/entrytypes/records",
)

register_entry_record(
    name="core-reference",
    record="httk.core.entry_types:Reference",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
)

# Earliest OPTIMADE specification version in which each standard property name
# is a property of this entry type (determined from the specification text at
# release tags v1.0.1, v1.1.0, v1.2.0, v1.3.0). Gates standard-name inference
# for services that publish no property-definition $id.
_REFERENCES_INTRODUCED_IN = {
    name: "1.0"
    for name in (
        "address",
        "annote",
        "authors",
        "bib_type",
        "booktitle",
        "chapter",
        "crossref",
        "doi",
        "edition",
        "editors",
        "howpublished",
        "id",
        "immutable_id",
        "institution",
        "journal",
        "key",
        "last_modified",
        "month",
        "note",
        "number",
        "organization",
        "pages",
        "publisher",
        "school",
        "series",
        "title",
        "type",
        "url",
        "volume",
        "year",
    )
}
# The files entry type itself first appears in OPTIMADE 1.2.
_FILES_INTRODUCED_IN = {
    name: "1.2"
    for name in (
        "atime",
        "checksums",
        "ctime",
        "description",
        "id",
        "immutable_id",
        "last_modified",
        "media_type",
        "modification_timestamp",
        "mtime",
        "name",
        "size",
        "type",
        "url",
        "url_stable_until",
        "version",
    )
}
_CALCULATIONS_INTRODUCED_IN = {name: "1.0" for name in ("id", "immutable_id", "last_modified", "type")}

register_optimade_entry_binding(
    name="core-reference",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references",
    backend="httk.core.optimade.entries:OptimadeReference",
    view="httk.core.optimade.entries:ReferenceView",
    query_fields=None,
    standard_property_versions=_REFERENCES_INTRODUCED_IN,
)
register_optimade_entry_binding(
    name="core-file",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
    backend="httk.core.optimade.entries:OptimadeFile",
    view="httk.core.optimade.entries:FileView",
    query_fields=None,
    standard_property_versions=_FILES_INTRODUCED_IN,
)
register_optimade_entry_binding(
    name="core-calculation",
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
    backend="httk.core.optimade.entries:OptimadeCalculation",
    view="httk.core.optimade.entries:CalculationView",
    query_fields=None,
    standard_property_versions=_CALCULATIONS_INTRODUCED_IN,
)
register_entry_record(
    name="core-file",
    record="httk.core.files:FileRecord",
    family="files",
    definition_id="https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files",
)
register_entry_record(
    name="core-calculation",
    record="httk.core.entry_types:Calculation",
    definition_id="https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations",
)
