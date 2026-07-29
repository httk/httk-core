"""Building a custom OPTIMADE entry type end to end

The OPTIMADE definitions guide walks through the pieces of the definition model
one at a time. This example does the opposite: it plays out the whole job a
database faces when it wants to serve properties of its own, start to finish, in
one runnable script, and prints the actual JSON that comes out at the end.

The scenario: a fictitious database, *Exampledb*, serves the standard OPTIMADE
`calculations` entry type but wants to attach three properties of its own to it
— a total energy, a lattice-vector array, and a classification string. Serving
custom properties correctly takes four steps.

**1. Claim a prefix.** OPTIMADE reserves unprefixed property names for the
standard; a database-specific property must be named `_<db>_<property>`. The
prefix is what routes the property's canonical `$id` to a URL the database
controls, so `register_definition_prefix` pairs the prefix with a base URL. The
prefix itself must be a lower-case alphanumeric token wrapped in single
underscores — `_exmpl_` is fine, `exmpl`, `_Exmpl_` and `_exmpl` are not.
`_httk_` and `_omdb_` come pre-registered, both under httk's ad-hoc namespace
at `schemas.httk.org/ad-hoc/`, which is separate from the
published definitions at `schemas.httk.org/defs/`: a synthesized `$id` names a
property that is not published anywhere, and should not pretend otherwise.

**2. Generate the property definitions.** `PropertyDefinition.from_simple`
builds a full, self-describing definition from a compact description: a name, a
human-readable `description`, and a `fulltype`. The `fulltype` grammar covers
`string`, `integer`, `float`, `boolean`, `timestamp`, `dict`, and nested lists
spelled out in words — `list of list of float` for a 3x3 array. Array
properties additionally take `dimensions` (named axes and their sizes) and a
`unit`; both surface in the generated document, and `dimensions` also causes a
`list_axes` metadata definition to be generated automatically.

The result is *implementation-neutral*: it describes the property,
not how any one deployment serves it. Per-deployment flags — is this property
sortable? is it in the response by default? — are layered on separately with
`with_implementation`, which returns a new definition and leaves the original
untouched.

**3. Extend the entry type.** `EntryTypeDefinition.extended` merges the custom
properties into a *copy* of the standard definition. It refuses a name that
collides with an existing property, and refuses an unprefixed custom name
unless you explicitly pass `allow_unprefixed=True` — which is why step 1 has to
happen first. Both refusals are demonstrated below.

**4. Emit it.** `as_optimade()` renders a definition as the JSON document
OPTIMADE actually specifies: `$schema`, `$id`, `title`, `description`,
`x-optimade-type`, the JSON `type` (with `null` included exactly when the
property is nullable), `items` for lists, `x-optimade-unit`,
`x-optimade-dimensions`, and the `x-optimade-definition` format stamp. The
stamp reads `"1.2"` even for a v1.3 entry type such as `calculations`: the
definition *format* is versioned separately from the specification, and
httk-core's generator only emits features that already exist in format 1.2.
"""

import json
from typing import Any

from httk.core import (
    EntryTypeDefinition,
    PropertyDefinition,
    known_definition_prefixes,
    register_definition_prefix,
    standard_entry_type,
)

PREFIX = "_exmpl_"
BASE_URL = "https://schemas.example.org/ad-hoc/defs/properties"


def claim_prefix() -> None:
    """Step 1: register the database-specific prefix and its base URL."""
    print("== Step 1: claim a definition prefix ==")
    print("pre-registered prefixes:", known_definition_prefixes())
    register_definition_prefix(PREFIX, BASE_URL)
    print("after registering:      ", known_definition_prefixes())

    for bad in ("exmpl", "_Exmpl_", "_exmpl", "exmpl_"):
        try:
            register_definition_prefix(bad, BASE_URL)
        except ValueError:
            print(f"  rejected malformed prefix {bad!r}")
    print()


def build_properties() -> dict[str, PropertyDefinition]:
    """Step 2: generate the custom property definitions."""
    print("== Step 2: generate the custom property definitions ==")
    properties = {
        "_exmpl_total_energy": PropertyDefinition.from_simple(
            "_exmpl_total_energy",
            description="Total energy of the calculation.",
            fulltype="float",
            unit="eV",
        ),
        "_exmpl_lattice_vectors": PropertyDefinition.from_simple(
            "_exmpl_lattice_vectors",
            description="The three lattice vectors of the calculated cell.",
            fulltype="list of list of float",
            unit="angstrom",
            dimensions={"names": ["dim_lattice", "dim_spatial"], "sizes": [3, 3]},
        ),
        "_exmpl_wave_class": PropertyDefinition.from_simple(
            "_exmpl_wave_class",
            description="Altermagnetic wave class of the calculated material.",
            fulltype="string",
        ),
    }
    for name, definition in properties.items():
        print(f"  {name}: {definition.optimade_type}, unit={definition.unit}")
        print(f"      $id: {definition.definition_id}")

    # Per-deployment flags are an overlay; the neutral definition is unchanged.
    served = properties["_exmpl_total_energy"].with_implementation(sortable=True, response_default=False)
    print("  overlay on _exmpl_total_energy:", served.as_optimade()["x-optimade-implementation"])
    print(
        "  neutral original still has no overlay:",
        "x-optimade-implementation" not in properties["_exmpl_total_energy"].as_optimade(),
    )
    print()
    return properties


def extend_entry_type(properties: dict[str, PropertyDefinition]) -> EntryTypeDefinition:
    """Step 3: merge the custom properties into a copy of the standard entry type."""
    print("== Step 3: extend the standard 'calculations' entry type ==")
    calculations = standard_entry_type("calculations")
    print(f"standard 'calculations' describes {len(calculations.properties)} properties:")
    print("  ", ", ".join(calculations.properties))

    extended = calculations.extended(properties)
    print(f"extended entry type describes {len(extended.properties)} properties:")
    print("  ", ", ".join(extended.properties))
    print("the standard definition is untouched:", "_exmpl_total_energy" not in calculations.properties)

    # A name that collides with an existing property is refused ...
    try:
        calculations.extended({"id": PropertyDefinition.from_simple("id", description="dup")})
    except ValueError as exc:
        print("  collision refused:", exc)

    # ... and so is an unprefixed custom name, unless explicitly allowed.
    cogwheels = PropertyDefinition.from_simple("cogwheels", description="Cogwheels.", fulltype="integer")
    try:
        calculations.extended({"cogwheels": cogwheels})
    except ValueError as exc:
        print("  unprefixed name refused:", exc)
    print(
        "  allow_unprefixed=True lets it through:",
        "cogwheels" in calculations.extended({"cogwheels": cogwheels}, allow_unprefixed=True).properties,
    )
    print()
    return extended


def emit(extended: EntryTypeDefinition) -> None:
    """Step 4: render the definitions as OPTIMADE JSON documents."""
    print("== Step 4: as_optimade() ==")
    lattice_vectors: dict[str, Any] = extended.properties["_exmpl_lattice_vectors"].as_optimade()
    print("_exmpl_lattice_vectors as an OPTIMADE property definition:")
    print(json.dumps(lattice_vectors, indent=2, sort_keys=True))

    print()
    print("Whole-entry-type document keys:", sorted(extended.as_optimade()))


def main() -> None:
    claim_prefix()
    properties = build_properties()
    extended = extend_entry_type(properties)
    emit(extended)


if __name__ == "__main__":
    main()
