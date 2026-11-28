# Property definitions

The semantic vocabulary of *httk₂* is based on OPTIMADE property and entry-type
definitions: they are first-class, immutable Python objects in
`httk.core.property_definitions`, shared by storage, serving, and domain
modules. *httk-core* vendors the standard entry types (`references`, `files`,
`calculations`) and pairs them with ready-to-use record models:

```python
from httk.core import Reference, standard_entry_type

references = standard_entry_type("references")
print(references.description)
assert "title" in references.properties      # each one a PropertyDefinition

entry = Reference.create({"title": "A title", "doi": "10.1234/demo.2021.1"})
```

Custom properties are generated from a simple declaration and live under a
registered definition prefix, so they never collide with curated definitions:

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple(
    "_httk_custom_energy", fulltype="float", unit="eV", description="Total energy."
)
extended = standard_entry_type("calculations").extended({"_httk_custom_energy": energy})
```

The full guide, {doc}`details/property_definitions`, covers the vendoring
policy and provenance, canonical `$id`s and the definition-format stamp,
registering your own definition prefix, entry-type extension rules, how remote
schemas that publish no `$id` are completed to standard-property identities, and
the generated record models.

Units of generated properties are checked and documented by the OPTIMADE unit
engine; see {doc}`units`. They follow the OPTIMADE compound-unit grammar
(`eV/atom` is rejected; declare the normalization separately, see below), and
changing a declared unit does not require rebuilding a store.

## Normalization

A value normalized to some entity ("per atom", "per simulation cell") declares
it in the provider-specific property-definition key `x-httk-normalization`. The
OPTIMADE specification permits `x-<prefix>-<name>` keys in property definitions
and requires clients to ignore unknown ones. The key holds an object with a
required `per`, a singular lowercase noun phrase rendered as `"per " + per`,
and exactly one of:

- `field`: the served name of a sibling property on the same entry type whose
  `x-optimade-type` is `integer`; its value in an entry may be `null` (count
  unknown), e.g. `{"per": "atom", "field": "_httk_custom_natoms"}`;
- `count`: a positive integer constant, e.g. `{"per": "simulation cell", "count": 1}`.

The property value multiplied by the count is the extensive quantity for the
system the entry describes. Normalization never replaces `x-optimade-unit`: the
unit stays the physical unit of the value (`eV`). When the key is omitted or
`null`: "No normalization is declared, and thus none should be inferred. While
all normalizations SHOULD be declared, the description text may contain
undeclared normalizations."

```python
from httk.core import Normalization

per_atom = PropertyDefinition.from_simple(
    "_httk_custom_energy",
    fulltype="float",
    unit="eV",
    description="Energy per atom.",
    normalization=Normalization(per="atom", field="_httk_custom_natoms"),
)
assert per_atom.as_optimade()["x-httk-normalization"] == {"per": "atom", "field": "_httk_custom_natoms"}
assert per_atom.normalization.label == "per atom"
```
