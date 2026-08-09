# OPTIMADE property & entry-type definitions

OPTIMADE definitions are *httk₂*'s semantic vocabulary: first-class, immutable
objects describing field identity, type, shape, units, and meaning — shared by
storage, serving, and domain modules alike. *httk-core* vendors the standard
entry types (`references`, `files`, `calculations`) and pairs them with
ready-to-use record models:

```python
from httk.core import Reference, standard_entry_type

references = standard_entry_type("references")
print(references.description)
assert "title" in references.properties      # each one a PropertyDefinition

entry = Reference.create({"id": "ref-1", "type": "references", "title": "A title"})
```

Custom properties are generated from a simple declaration and live under a
registered definition prefix, so they never collide with curated definitions:

```python
from httk.core import PropertyDefinition

energy = PropertyDefinition.from_simple(
    "_httk_custom_energy", "float", unit="eV", description="Total energy."
)
extended = standard_entry_type("calculations").extended({"_httk_custom_energy": energy})
```

The full guide, {doc}`details/optimade_definitions`, covers the vendoring
policy and provenance, canonical `$id`s and the definition-format stamp,
registering your own definition prefix, entry-type extension rules, and the
generated record models.
