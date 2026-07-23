# OPTIMADE property & entry-type definitions

*httk-core* models OPTIMADE **property definitions** and **entry-type
definitions** as first-class, immutable Python objects in
`httk.core.property_definitions`, and pairs the standard entry types it vendors
with ready-to-use data models and entry providers in `httk.core.entry_types`.

A *property definition* is a self-describing document: it carries a property's
canonical `$id`, its OPTIMADE type and unit, its requirements, and a
human-readable description. An *entry-type definition* bundles the property
definitions of one entry type together with the entry type's own description.

## Vendoring policy

The authoritative, supported copies of the standard OPTIMADE entry-type
definitions are the JSON files checked in under
`src/httk/core/optimade_defs/` (`references`, `files`, `calculations`). They are
distributed by the Materials-Consortia under the MIT License (see the `LICENSE`
next to them). *httk-core* supports exactly the checked-in versions; the
`README.md` in that directory records their provenance, and `make optimade-defs`
re-fetches them from the network (the only source task that does). Ordinary
builds and tests read the committed copies offline.

## Loading a standard definition

`standard_entry_type` returns the vendored definition for one of httk-core's
standard entry types (`references`, `files`, `calculations`):

```python
from httk.core import standard_entry_type

references = standard_entry_type("references")
print(references.description)
print(len(references.properties), "properties")
assert len(references.properties) == 30
```

Each property is a `PropertyDefinition`. Vendored definitions keep their
canonical `$id`s — note the mix of *core* (shared) and entry-scoped identifiers —
and every one carries the `"1.2"` definition-format stamp:

```python
from httk.core import standard_entry_type

references = standard_entry_type("references")
assert references.properties["id"].definition_id.endswith("/properties/core/id")
assert references.properties["title"].definition_id.endswith("/optimade/references/title")
assert all(prop.format_version == "1.2" for prop in references.properties.values())
```

The `"1.2"` stamp is deliberate: httk-core's generator emits only features that
already exist in format `1.2` of the OPTIMADE property-definition schema, and
the definition *format* is versioned in lockstep with the specification —
re-stamped only when a definition actually uses newer features. That is why even
`calculations` (a v1.3 entry type) keeps `"1.2"`-format property definitions.

## Generating a custom property

`PropertyDefinition.from_simple` generates an implementation-neutral definition
from a compact description. A database-specific property must carry a recognized
prefix (`_httk_` or `_omdb_`), which routes its `$id` under `httk.org`:

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple(
    "_httk_total_energy",
    description="Total energy of the calculation.",
    fulltype="float",
)
doc = energy.as_optimade()
assert doc["$id"] == "https://httk.org/optimade/defs/properties/_httk_total_energy"
assert doc["x-optimade-type"] == "float"
assert doc["type"] == ["number", "null"]
```

Per-deployment `sortable`/`response-default` flags are layered on separately, so
the definition itself stays neutral:

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple("_httk_total_energy", description="E", fulltype="float")
served = energy.with_implementation(sortable=False, response_default=True)
assert served.as_optimade()["x-optimade-implementation"] == {"sortable": False, "response-default": True}
# The original is untouched:
assert "x-optimade-implementation" not in energy.as_optimade()
```

## Extending an entry type

`EntryTypeDefinition.extended` merges custom properties into a copy of a standard
definition. Unprefixed custom names are rejected (OPTIMADE reserves them for
standard properties):

```python
from httk.core import PropertyDefinition, standard_entry_type

energy = PropertyDefinition.from_simple("_httk_total_energy", description="E", fulltype="float")
calculations = standard_entry_type("calculations").extended({"_httk_total_energy": energy})
assert "_httk_total_energy" in calculations.properties

try:
    standard_entry_type("calculations").extended(
        {"cogwheels": PropertyDefinition.from_simple("cogwheels", description="w", fulltype="integer")}
    )
except ValueError as exc:
    assert "_httk_" in str(exc)
```

## Entry types and providers

`httk.core.entry_types` provides a frozen dataclass and an
`httk.core.EntryProvider` for each standard entry type. A provider maps
`{id: record}` to the neutral contract: the definition becomes the served
schema, `columns()` names the served subset, and `records()` yields JSON-able
rows.

```python
from httk.core import Reference, ReferenceEntryProvider

provider = ReferenceEntryProvider(
    {
        "ref-1": Reference(title="A study of gallium titanium compounds", doi="10.1234/demo.2021.1"),
        "ref-2": {"title": "Silicon dioxide polymorphs revisited", "doi": "10.1234/demo.2019.7"},
    }
)

entry_types = provider.entry_types()
assert list(entry_types) == ["references"]

columns = provider.columns("references")
assert columns["id"] == "__id" and columns["type"] == "type"

records = list(provider.records("references"))
assert {r["__id"] for r in records} == {"ref-1", "ref-2"}
assert records[0]["type"] == "references"
```

The three providers self-register (as `core-references`, `core-files`,
`core-calculations`) when `httk.core` is imported, so a serving module can
discover them through the registry:

```python
import httk.core
from httk.core import known_entry_providers

assert {"core-references", "core-files", "core-calculations"} <= set(known_entry_providers())
```
