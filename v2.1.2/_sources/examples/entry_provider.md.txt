# Implementing an `EntryProvider`: the contract *httk-core* owns

`httk.core.EntryProvider` is the neutral seam between a module that *has* data
and a module that *serves* it. A domain module (say a materials database)
implements the contract; a serving module (say *httk-serve*) consumes it.
Neither imports the other — they meet at this abstract base class and its small
registry. Nothing in the contract is specific to materials science, or even to
OPTIMADE.

A provider answers three questions per entry type, and optionally a fourth
and fifth:

`entry_types()`
    *What do you serve, and what does it mean?* Returns a mapping of entry-type
    name to `EntryTypeDefinition` — the same first-class definition objects
    described in the OPTIMADE definitions guide. A definition may describe more
    properties than the provider actually serves; it is the schema, not the
    selection.

`property_keys(entry_type)`
    *Where does each served property live in a record?* Maps a served property
    name onto the key it is stored under. This is the selection: exactly these
    property names are served, and every one of them must be described by the
    entry type's definition. The map must always cover at least `id` and
    `type`. The indirection matters — a provider's records usually already
    exist in some internal shape, and the map lets `id` be read from a record
    key called `__id` without renaming anything.

`records(entry_type)`
    *The data.* Plain JSON-able mappings keyed by the record keys named above:
    strings, numbers, booleans, `None`, and nested lists/dicts of those. An
    iterable, so a real provider can stream from a database instead of
    materializing everything.

`relationships(entry_type)`
    *Optional.* Maps an entry id to a flat tuple of `RelatedEntry` values, each
    naming a related entry by its type and id, with optional `description` and
    `role` metadata (OPTIMADE v1.2 and v1.3 respectively), an optional `label`
    (the OPTIMADE relation-object label, served as `meta._httk_label`), and an
    optional `relationship` — a wire-form semantic relationship key. It is flat
    on purpose: the serving layer groups by `relationship or entry_type` (a
    `None` relationship falls back to grouping by the target's entry type). The
    base-class default returns an empty mapping.

`reverse_relationships()`
    *Optional, and takes no argument.* The derived reverse of edges a provider
    owns (e.g. run provenance edges), for entries that *other* types serve.
    Unlike `relationships` it is one level deeper and not scoped to a single
    entry type: it returns a nested mapping keyed first by the *target* entry
    type, then by target id, to a flat tuple of `RelatedEntry` values. The
    serving layer append-merges these onto those targets' forward blocks so a
    provider can expose both directions of a semantic edge. The base-class
    default returns an empty mapping.

The example below implements a `widgets` provider with two records and a
relationship to a `references` entry, then exercises the contract exactly as a
consumer would: definitions first, then the property-key map, then the records
extracted through that map.

Finally it shows the **registry**. `register_entry_provider` records a *lazy*
`"module:callable"` reference to a factory, never a live provider, because
providers need data and only the application knows where that data comes from.
A consumer lists what is available with `known_entry_providers()` and resolves
the reference only when it decides to build one.

```{literalinclude} ../../examples/entry_provider.py
:language: python
:lines: 66-
```
