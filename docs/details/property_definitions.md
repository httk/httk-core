# Property definitions

The semantic vocabulary of *httk₂* is based on OPTIMADE property and entry-type
definitions: they are first-class, immutable Python objects in
`httk.core.property_definitions`, and pair the standard entry types *httk-core*
vendors with ready-to-use, stdlib-only data models in `httk.core.entry_types`.
The `httk.core.EntryProvider` implementations that serve those models live in
the *httk-store* module.

For the short practical overview, see {doc}`/property_definitions`.

A *property definition* is a self-describing document: it carries a property's
canonical `$id`, its OPTIMADE type and unit, its requirements, and a
human-readable description. An *entry-type definition* bundles the property
definitions of one entry type together with the entry type's own description.

## Vendoring policy

The authoritative, supported copies of the standard OPTIMADE entry-type
definitions are the JSON files checked in under
`src/httk/registry/schemas/core/` (`references`, `files`, `calculations`). They
are distributed by the Materials-Consortia under the MIT License (see the
`LICENSE` next to them). *httk-core* supports exactly the checked-in versions;
the `README.md` in that directory records their provenance, and
`make optimade-defs` re-fetches them from the network. Ordinary builds and
tests read the committed copies offline.

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
canonical `$id`s — note the mix of *core* (shared) and entry-scoped identifiers
— and every one carries the `"1.2"` definition-format stamp:

```python
from httk.core import standard_entry_type

references = standard_entry_type("references")
assert references.properties["id"].definition_id.endswith("/properties/core/id")
assert references.properties["title"].definition_id.endswith("/optimade/references/title")
assert all(prop.format_version == "1.2" for prop in references.properties.values())
```

The `"1.2"` stamp reflects that httk-core's generator emits only features that
already exist in format `1.2` of the OPTIMADE property-definition schema, and
the definition *format* is versioned in lockstep with the specification —
re-stamped only when a definition actually uses newer features. That is why
even `calculations` (a v1.3 entry type) keeps `"1.2"`-format property
definitions.

## Generating a custom property

`PropertyDefinition.from_simple` generates an implementation-neutral definition
from a compact description. A database-specific property must carry a
registered prefix. The `_httk_` prefix is pre-registered under the `httk.org`
base.

Machine-generated and on-the-fly names use a reserved `custom_` sub-namespace
inside that prefix: `_<prefix>_custom_<name>`, where `<prefix>` is the token in
the registered prefix. Thus httk's names are `_httk_custom_<name>`; they cannot
collide with curated `_httk_*` definitions outside that sub-namespace.
*httk-store*'s `auto_definition` follows the same convention by default.

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple(
    "_httk_custom_total_energy",
    description="Total energy of the calculation.",
    fulltype="float",
)
doc = energy.as_optimade()
assert doc["$id"] == "https://schemas.httk.org/ad-hoc/defs/properties/_httk_custom_total_energy"
assert doc["x-optimade-type"] == "float"
assert doc["type"] == ["number", "null"]
```

## Registering a definition prefix

The recognized database-specific prefixes are held in a small registry.
`_httk_` is pre-registered under the `httk.org` base. A database serving its
own custom properties registers its prefix once, giving the base URL under
which those properties' `$id`s are minted; a prefix must be a lower-case
alphanumeric token wrapped in single underscores:

```python
from httk.core import (
    PropertyDefinition,
    known_definition_prefixes,
    register_definition_prefix,
    standard_entry_type,
)

register_definition_prefix("_exmpl_", "https://schemas.example.org/ad-hoc/defs/properties")
assert "_exmpl_" in known_definition_prefixes()

# from_simple routes the prefixed name's $id under the registered base:
wave_class = PropertyDefinition.from_simple(
    "_exmpl_wave_class", description="Altermagnetic wave class.", fulltype="string"
)
assert wave_class.as_optimade()["$id"] == "https://schemas.example.org/ad-hoc/defs/properties/_exmpl_wave_class"

# ...and extended() accepts the registered prefix as a custom property:
references = standard_entry_type("references").extended({"_exmpl_wave_class": wave_class})
assert "_exmpl_wave_class" in references.properties
```

An invalid prefix (e.g. `"exmpl"`, `"_Exmpl_"`, `"exmpl_"`) raises a clear
`ValueError`, and re-registering an existing prefix overwrites its base.

Per-deployment `sortable`/`response-default` flags are layered on separately,
so the definition itself stays neutral:

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple("_httk_custom_total_energy", description="E", fulltype="float")
served = energy.with_implementation(sortable=False, response_default=True)
assert served.as_optimade()["x-optimade-implementation"] == {"sortable": False, "response-default": True}
assert served.definition_id == energy.definition_id
# The original is untouched:
assert "x-optimade-implementation" not in energy.as_optimade()
```

## Extending an entry type

`EntryTypeDefinition.extended` merges custom properties into a copy of a
standard definition. Unprefixed custom names are rejected (OPTIMADE reserves
them for standard properties):

```python
from httk.core import PropertyDefinition, standard_entry_type

energy = PropertyDefinition.from_simple("_httk_custom_total_energy", description="E", fulltype="float")
standard = standard_entry_type("calculations")
calculations = standard.extended({"_httk_custom_total_energy": energy})
assert "_httk_custom_total_energy" in calculations.properties
assert calculations.definition_id is None
assert calculations.extends_id == standard.definition_id

try:
    standard.extended(
        {"cogwheels": PropertyDefinition.from_simple("cogwheels", description="w", fulltype="integer")}
    )
except ValueError as exc:
    assert "_httk_" in str(exc)
```

## Extension and `$id`

`EntryTypeDefinition.extended()` creates a new entry-type document. It drops
the source document's `$id`, because the extended document is no longer that
identified standard resource. Its `extends_id` retains the original standard
IRI; chained extensions keep that original IRI. Consequently, *httk-serve*
emits a `describedby` link only when `definition_id` exists, so an extended
entry type has no `describedby` link for the standard `$id`.

`PropertyDefinition.with_implementation()` has a different identity policy.
It keeps the standard `$id` and `x-optimade-definition`, because implementation
annotations do not change the definition's meaning. The vendored [OPTIMADE v1.2
Property Definitions meta-schema](https://schemas.optimade.org/meta/v1.2/optimade/property_definition.json)
says definitions “SHOULD be regarded as the same if they only differ by”
changes to `x-optimade-implementation`. The specification's identity rule — a
redefinition “MUST change the `$id`” — therefore applies when the meaning
changes, not to these deployment annotations.

For authors: if a definition's meaning changes, give it a new IRI and never
re-serve the modified definition under the standard `$id`.

## Entry-type record models

`httk.core.entry_types` provides one frozen dataclass per standard entry type
(`Reference`, `File`, `Calculation`), each carrying a field for every non-core
property of its standard. `id` comes from a provider's mapping key and `type` is
constant, so neither is a dataclass field. `create` accepts either an instance
or a plain mapping (unknown keys are rejected), which is how a provider ingests
records:

```python
from httk.core import Reference

ref = Reference.create(
    {"title": "A study of gallium titanium compounds", "doi": "10.1234/demo.2021.1"}
)
assert ref.title == "A study of gallium titanium compounds"
assert ref.year is None  # every non-core property defaults to None

# create() is idempotent on an existing instance:
assert Reference.create(ref) is ref
```

These models use only the standard library. The `httk.core.EntryProvider`
implementations that map `{id: record}` mappings of them onto the neutral
provider contract — and self-register as `store-references`, `store-files`, and
`store-calculations` — live in the *httk-store* module, together with
property-definition validation built on the definitions above. That keeps
httk-core a dependency-free layer of *contracts and models*, with the concrete
*capabilities* provided by the modules built on top of it.
