"""Implementing an `EntryProvider`: the contract *httk-core* owns

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
"""

from collections.abc import Iterable, Mapping
from typing import Any

from httk.core import (
    EntryProvider,
    EntryTypeDefinition,
    PropertyDefinition,
    RelatedEntry,
    known_entry_providers,
    register_entry_provider,
)


class WidgetProvider(EntryProvider):
    """A minimal provider serving two records of one `widgets` entry type."""

    #: The records, in whatever internal shape the provider already had them.
    WIDGETS: tuple[dict[str, Any], ...] = (
        {"__id": "w-1", "type": "widgets", "cogs": 3},
        {"__id": "w-2", "type": "widgets", "cogs": 5},
    )

    def entry_types(self) -> Mapping[str, EntryTypeDefinition]:
        return {
            "widgets": EntryTypeDefinition(
                "widgets",
                "A widget: the smallest thing this demo database knows about.",
                {
                    "id": PropertyDefinition.from_simple("id", description="The widget id.", required_response=True),
                    "type": PropertyDefinition.from_simple(
                        "type", description="The entry type.", required_response=True
                    ),
                    "cogs": PropertyDefinition.from_simple(
                        "cogs", description="Number of cogs in the widget.", fulltype="integer"
                    ),
                },
            )
        }

    def property_keys(self, entry_type: str) -> Mapping[str, str]:
        # Served property name -> record key. Note "id" is stored as "__id".
        return {"id": "__id", "type": "type", "cogs": "cogs"}

    def records(self, entry_type: str) -> Iterable[Mapping[str, Any]]:
        return self.WIDGETS

    def relationships(self, entry_type: str) -> Mapping[str, tuple[RelatedEntry, ...]]:
        return {
            "w-1": (
                RelatedEntry("references", "ref-1", description="The paper introducing the widget"),
                RelatedEntry("files", "f-1", role="input"),
            ),
        }


def make_widget_provider() -> WidgetProvider:
    """Factory referenced by the registry entry below."""
    return WidgetProvider()


def show_contract(provider: EntryProvider) -> None:
    """Walk the contract the way a consumer does: definitions, keys, records."""
    print("== The served entry types and their definitions ==")
    for name, definition in provider.entry_types().items():
        print(f"{name}: {definition.description}")
        for property_name, property_definition in definition.properties.items():
            nullable = "nullable" if property_definition.nullable else "required in response"
            print(f"  - {property_name}: {property_definition.optimade_type} ({nullable})")
            print(f"      $id: {property_definition.definition_id}")
    print()

    print("== The served subset, and how it maps onto record keys ==")
    property_keys = provider.property_keys("widgets")
    for property_name, record_key in property_keys.items():
        print(f"  {property_name!r} is found under record key {record_key!r}")
    print()

    print("== The records, read through the property-key map ==")
    for record in provider.records("widgets"):
        served = {name: record[key] for name, key in property_keys.items()}
        print("  ", served)
    print()

    print("== Relationships ==")
    relationships = provider.relationships("widgets")
    for entry_id, related in relationships.items():
        for entry in related:
            extra = [part for part in (entry.description, entry.role) if part is not None]
            print(f"  {entry_id} -> {entry.entry_type}/{entry.id}" + (f"  ({'; '.join(extra)})" if extra else ""))
    for entry_id in (record["__id"] for record in WidgetProvider.WIDGETS):
        if entry_id not in relationships:
            print(f"  {entry_id} -> (no related entries)")
    print()


def show_registry() -> None:
    """Registration records a lazy factory reference, not a live provider."""
    print("== The entry-provider registry ==")
    print("before:", known_entry_providers() or "(none registered)")
    register_entry_provider(name="demo-widgets", factory=f"{__name__}:make_widget_provider")
    print("after: ", known_entry_providers())
    print("The value stored is the string 'module:callable'; a consumer resolves and")
    print("calls it only when it actually needs a provider instance.")


def main() -> None:
    show_contract(WidgetProvider())
    show_registry()


if __name__ == "__main__":
    main()
