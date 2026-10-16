# Building a custom OPTIMADE entry type end to end

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
`_httk_` comes pre-registered under httk's ad-hoc namespace at
`schemas.httk.org/ad-hoc/`; generated httk custom names use its
`_httk_custom_*` sub-namespace. This is separate from the
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

```{literalinclude} ../../examples/property_definitions.py
:language: python
:lines: 55-
```
