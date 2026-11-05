# Declarative entry records

Applications can define served data with frozen dataclasses, without repeating
identifier fields, plugin registrations, or direct field projections. These
helpers are available on the current development branch; they require a release
containing this API when installing from PyPI.

```python
from typing import Annotated
from httk.core import DataEntryRecord, Normalization, Property, entry_record

@entry_record("example.measurement")
class Measurement(DataEntryRecord):
    energy: Annotated[
        float,
        Property(
            description="Energy per atom.",
            unit="eV",
            normalization=Normalization(per="atom", field="natoms"),
        ),
    ]
    natoms: Annotated[int | None, Property(description="Number of atoms in the cell.")]
    label: str

measurement = Measurement(-1.2, 2, "sample-1")
assert measurement.id is None
assert measurement.energy == -1.2
assert Measurement.entry_type_definition().served_form().name == "_httk_records"
energy = Measurement.__httk_property_definitions__["_httk_custom_energy"]
assert energy.as_optimade()["x-httk-normalization"] == {"per": "atom", "field": "_httk_custom_natoms"}
```

`EntryRecord` supplies keyword-only `id`, `immutable_id`, and `last_modified`
fields. They are excluded from equality and content identity. `DataEntryRecord`
selects the `_httk_records` family without prescribing any scientific fields.
The existing `DataRecord` remains the separate model for one canonical JSON
property value; its constructors and identities are unchanged.

`DerivedDataRecord` stores a statistic or other derivation of a declared
property, such as a standard error or an RMSE. Its `definition_id` and `name`
name the base property and the identity-bearing `derivation` field holds the
derivation-term IRI that qualifies it
(e.g. `https://schemas.httk.org/defs/v0.1/derivations/standard_error`).
Derived values are a separate record type so that no `DataRecord` content
identity changes. A store opened before this record type existed adds it with
the additive declaration upgrade (`upgrade=True`).

`entry_record` creates the frozen dataclass, so a separate `@dataclass` is not
needed. Its explicit name pins the logical content identity independently of the
Python class name or module. Physical storage names are derived deterministically
from that identity. A directly declared `StorageInfo` can supply indexes or an
explicit physical name. Every concrete subclass needs its own decorator and
identity; generated property mappings are specific to that class.

Only fields marked with `Property` or `PropertyDefinition` are published as
attributes. In the example, `energy` becomes `_httk_custom_energy` and `natoms`
becomes `_httk_custom_natoms`, while `label` remains local bookkeeping and still contributes to content identity.
Definitions, exact direct-field filtering, and sorting are generated for `str`,
`int`, `float`, and `bool`, including nullable variants. Scientific meaning and
units remain explicit. Other values, including exact rationals needing a
presentation conversion, use the existing explicit projection API.

A `Property` unit follows the OPTIMADE compound-unit grammar (`*` between
code-point-ordered factors, `^-1` for division, e.g. `angstrom^-1*eV`) and is
checked when the record class is declared. Per-atom or per-formula-unit
normalization is not part of the unit, so `eV/atom` is rejected in favour of
`unit="eV"` plus `normalization=Normalization(per="atom", field="natoms")`.
In `Property`, `field` names a sibling field of the same record by its Python
attribute name; it must itself be a served `int` (optionally `| None`) field,
and is emitted under its served name. A constant count, such as
`Normalization(per="simulation cell", count=1)`, is emitted unchanged. A
curated `PropertyDefinition` declaring a `field` normalization requires another
field of the record serving that name as an integer. Bad references fail when
the class is declared; see {doc}`property_definitions` for the served
`x-httk-normalization` contract. Changing a declared unit does not require
rebuilding a store.

An existing property definition can be attached directly:

```python
from httk.core import PropertyDefinition

energy_definition = PropertyDefinition.from_simple(
    "_httk_custom_energy", description="Energy per atom.", fulltype="float", unit="eV"
)

@entry_record("example.energy-result")
class EnergyResult(DataEntryRecord):
    energy: Annotated[float, energy_definition]
```

The definition's type must match the Python scalar annotation, and nullable
Python fields cannot use a non-nullable definition. Custom names must carry a
registered provider prefix. Conflicting declarations fail at decoration time.

A curated, registered definition can be used directly. It is served under its
registered prefix, keeping its `$id`, unit and description:

```python
from httk.core import load_property_definition

@entry_record("example.curated-result")
class CuratedResult(DataEntryRecord):
    total_energy: Annotated[float, load_property_definition("https://schemas.httk.org/defs/v0.1/properties/core/total_energy")]

assert "_httk_total_energy" in CuratedResult.entry_type_definition().properties
```

Record-valued fields remain ordinary references; they do not need `StrongLink`.
When their target is a served family, *httk-store* and *httk-serve* expose them as
OPTIMADE relationships. The storage reference pins the nested record; it is not
a mutable weak link.

The decorator does not register global plugins. With *httk-store*, pass
`records=[Measurement]` when creating **and reopening** the store. Keep the record
definition in an importable module shared by your importer and server. The store
checks the supplied classes against its persisted layout; it does not import
Python classes or execute code named by the database.

See the [three-file serving walkthrough](https://docs.httk.org/dev/develop/serving-data.html)
for CIF structures, JSON results, SQLite storage, and a separate serving script.
The API is documented in {mod}`httk.core.entry_records`.
