# Registries and plugin discovery

`httk-core` keeps capability registration separate from capability imports. A
capability module ships a package below one of the reserved namespaces:
`httk.registry.<tier>.<module>`. The four tiers are:

- `cli` for top-level command registrations;
- `entries` for entry providers, records, families, and OPTIMADE bindings;
- `io` for readers, writers, format adapters, and serializers;
- `schemas` for vendored definition documents.

The tier directories are PEP 420 namespace packages: they have no
`__init__.py`. Discovery walks exactly these four tiers. It imports each
registration package eagerly, so installation and registration errors fail
fast. Registration packages must only record lazy references: `"module:callable"`
for code and `"package:filename.json"` for schema resources. They must not
resolve handlers or load resource data while being imported.

For example, *httk-io* ships `httk.registry.io.io` for its readers and writer;
*httk-atomistic* ships format adapters and serializers under
`httk.registry.io.atomistic`, entry registrations under
`httk.registry.entries.atomistic`, and schemas under
`httk.registry.schemas.atomistic`; *httk-workflow* ships
`httk.registry.cli.workflow`.

(readers)=
## Readers

`httk.core.load` dispatches by the filename's extension, or by an exact
basename when no registered extension matches. Matching is case-insensitive.
At most one recognized compression suffix is stripped before dispatch, while
the reader receives the original filename. `has_reader_for` tests dispatch
without loading a file.

```python
from httk.core import load, register_reader
from httk.core.register import known_extensions, known_filenames

register_reader(
    name="demo",
    reader="example_package.readers:read_demo",
    extensions=(".demo",),
    filenames=("DEMOCAR",),
)

assert ".demo" in known_extensions()
assert "democar" in known_filenames()
load("sample.demo.gz")
```

Reader results may be neutral mappings tagged with a string `"format"`. A
registered format adapter converts such a mapping to a domain object;
`load(..., raw=True)` keeps the neutral payload. Unknown format tags and
non-mapping results pass through unchanged.

```python
from httk.core import register_format_adapter, register_format_serializer

register_format_adapter(
    name="demo-domain",
    adapter="example_package.adapters:from_demo",
    formats=("demo",),
)
register_format_serializer(
    format="demo",
    serializer="example_package.adapters:to_demo",
)
```

See also {doc}`datastreams` for transparent compressed input.

## Writers

`register_writer` mirrors reader registration. It requires a `format` tag and
can select a writer by extensions and/or exact basenames:

```python
from httk.core import register_writer, save

register_writer(
    name="demo-writer",
    writer="example_package.writers:write_demo",
    format="demo",
    extensions=(".demo",),
)
save(obj, "output.demo")
```

`save` uses the destination name or an explicit `format=` to select the
writer. A non-neutral object is first passed through the registered format
serializer; a neutral mapping with the matching `"format"` tag is written as
is. `known_writers` lists registered extension and basename keys.

(save-view-semantics)=

### Save semantics

`save` writes the underlying data; views are transparent. A view presents its
backend through another interface and holds no data of its own, so
`save(view, dest)` and `save(backend, dest)` write the same file.
Exact-by-default means the original representation is the source of truth:
when the destination format matches a backend's retained native representation
(for example, a POSCAR-backed structure saved as `.vasp`), the writer receives
the original data verbatim and the result is byte-exact. When the destination
format differs (the same view saved as `.cif`), the registered format
serializer converts from the presented domain data like any other conversion.
To deliberately save the presentation instead, shed it explicitly first:
`save(unview(v), dest)` (or `coerce(v, ...)`), following the four-verb view
grammar.

The `format=` keyword overrides destination-name dispatch:

```python
save(obj, "data.out", format="vasp-poscar")
```

A mapping whose `"format"` key equals the selected tag is written verbatim;
other objects go through the registered format serializer for that tag.

To discover the available dispatch options, use
`httk.core.register.known_writer_formats()` for the tags accepted by
`format=`, `known_writers()` for writer destination keys, and
`has_writer_for(name)` to probe destination-name dispatch. The load direction
has the corresponding `known_format_adapters()` accessor.

```python
from httk.core.register import known_writer_formats

assert known_writer_formats() == sorted(known_writer_formats())
```

## Entry providers, records, families, and bindings

`register_entry_provider(*, name, factory)` records a lazy factory for an
{class}`httk.core.entry_provider.EntryProvider`. The factory is called by the
application because providers usually need application data.

Entry records and families are also lazy references:

```python
from httk.core import register_entry_family, register_entry_record

register_entry_family(
    name="demo-family",
    family="example_package.entries:DemoFamily",
    definition_id="https://schemas.example.org/defs/demo",
)
register_entry_record(
    name="demo-record",
    record="example_package.entries:DemoRecord",
    family="demo-family",
    definition_id="https://schemas.example.org/defs/demo",
)
```

`known_entry_families`, `entry_family_info`, and `resolve_entry_family`
inspect or resolve families. `known_entry_records`, `entry_record_info`, and
`resolve_entry_record` provide the corresponding record operations. Resolution
imports the class only when requested.

`register_optimade_entry_binding` associates one exact entry-type definition
IRI with lazy `backend` and `view` references. Its optional
`property_decoders` mapping and `query_fields` tuple also contain definition
IRIs and lazy references. `known_optimade_entry_bindings` lists the registered
IRIs, while `optimade_entry_binding` returns metadata without importing the
binding's classes.

## Schema definition resources

Schema registration points at vendored JSON resources rather than loading
them during discovery:

```python
from httk.core import (
    load_entry_type_definition,
    load_property_definition,
    register_entry_type_definition,
    register_property_definition,
)

register_entry_type_definition(
    definition_id="https://schemas.example.org/defs/demo",
    resource="example_package.schemas:demo.json",
)
register_property_definition(
    definition_id="https://schemas.example.org/defs/demo/name",
    resource="example_package.schemas:demo_name.json",
)

entry_type = load_entry_type_definition("https://schemas.example.org/defs/demo")
property_definition = load_property_definition("https://schemas.example.org/defs/demo/name")
```

`known_entry_type_definitions` and `known_property_definitions` list the
registered IRIs. The resource string is `package:filename.json`; loading
verifies that the document `$id` matches the registered IRI.

## CLI commands

`register_cli_command(name, handler, summary)` adds a lazy top-level command.
The handler may be a callable or a `"module:callable"` reference. The
registration package belongs under `httk.registry.cli.<module>`. The CLI
surface and user-facing workflow are documented in {doc}`cli`; see also
{ref}`readers` for the analogous IO registration pattern.

## Definition prefixes

`register_definition_prefix(prefix, id_base)` registers a database-specific
OPTIMADE property-name prefix. `known_definition_prefixes` lists the current
prefixes. Prefixes are lower-case alphanumeric tokens wrapped in underscores;
the built-in `_httk_` prefix is already registered. See
{doc}`optimade_definitions`.

## Compression codecs

`register_compression` adds a {class}`httk.core.datastream.compression.CompressionCodec`
with a name, filename extensions, magic prefixes, and a decompression stream
function. `known_compressions` lists codec names. The built-in selection rules
and `CompressionCodec` fields are described in {doc}`datastreams`.

## Leaf codecs

`register_leaf_codec` adds a {class}`httk.core.vectors.leaf_codecs.LeafCodec`
for vector leaf conversion. `known_leaf_codecs` lists codec names; the vector
guide covers the built-in codecs and their options. See {doc}`vectors`.

(coercers)=
## Coercers

`register_coercer(coercer, target)` appends a coercer to the global coercion
registry. The callable has the shape `(value, target) -> converted value | None`;
`target` declares what it can coerce *into* — a class, a tuple of classes, or
`typing.Any` for a fully general coercer. On lookup,
{func}`httk.core.views.coercion.coerce_view` first tries a direct view conversion
when the requested class is a `View` subclass, then tries registered coercers
whose declared targets match the requested class, in registration order.
Returning `None` declines the conversion; `TypeError` is raised if every
coercer declines it. Strict {func}`httk.core.views.coercion.coerce` resolves
through the same registry and then additionally sheds view results (for
non-`View` targets) and validates that the final result is an instance of the
requested target. See the four-verb table in {doc}`view_backend_pattern`.

## Canonical encoders

`register_canonical_encoder(python_type, encoder)` registers one deterministic
encoder for an exact custom Python type. The encoder returns the value used by
canonical storage identity and content IDs. Duplicate type registrations are
errors; see {func}`httk.core.storage.identity.register_canonical_encoder`.

### Canonical format v2

`canonical_form` emits compact, ASCII-escaped JSON with sorted object keys.
Every standalone record has this shape, with field pairs sorted by name:

```json
{"fields":[["field",{"type":"string","value":"value"}]],"identity_name":"logical.name","type":"record","version":2}
```

An annotated record reached as a record field, list/tuple element, or typed
mapping value is a Merkle reference rather than an embedded record:

```json
{"content_id":"<64 lowercase hex characters>","type":"record_ref"}
```

The reference digest is SHA-256 of the child's own canonical record JSON,
including its version-2 header, computed in the same traversal context. The v2
node table is:

| Python value | Canonical node payload |
| --- | --- |
| `None` | `{"type":"null"}` |
| `bool` | `{"type":"bool","value":<JSON boolean>}` |
| `int` | `{"type":"int","value":"<decimal integer>"}` |
| `Fraction`, finite `Decimal`, direct `FracScalar` | `{"type":"rational","value":"p/q"}` |
| finite `float` | `{"type":"float","value":"<float.hex() text>"}` |
| `str` / `bytes` | `string` with the text / `bytes` with lowercase hexadecimal text |
| `date` | `date` with ISO text |
| `datetime` | `datetime` with microsecond ISO text and an `aware` Boolean; aware values are converted to UTC |
| `FracVector` | `frac_vector` with the v1 structural `denominator` and nested `nominators` payload |
| `SurdScalar`, `SurdVector` | v1 structural `surd_scalar` / `surd_vector` with dimension and radicand/coefficient pairs |
| list / tuple | `list` / `tuple` with an ordered array of canonical nodes |
| string-keyed mapping | `mapping` with sorted `[key, canonical node]` pairs |
| registered exact custom type | `custom` with `python_type` and a canonically tagged encoder result |
| standalone record / annotated child record | version-2 `record` / `record_ref` as above |

The rational grammar is exactly
`f"{fraction.numerator}/{fraction.denominator}"` after conversion to
`Fraction`: it is reduced, the denominator is positive and always present, so
examples include `"0/1"`, `"-3/2"`, and `"5/1"`. `Decimal` converts through
`Fraction(decimal)`, preserving the documented `Decimal` ≡ `Fraction`
equivalence. `FracVector`, `SurdVector`, and `SurdScalar` deliberately retain
their structural v1 payloads.

The format is not injective after record children are replaced by digests. Its
guarantee is **computational binding**: producing two distinct well-formed
canonical value trees, modulo the documented deliberate equivalences
(shared-vs-duplicated equal children, `IdentitySkip` exclusions,
`identity_name`-based record unification, `Decimal` ≡ `Fraction`, unregistered
builtin-subclass leaf unification, and annotation-normalized list/tuple values),
with equal digests requires a SHA-256 collision. `record_ref` provides sound
domain separation: user strings, mappings, and custom values remain enclosed
in their own tagged nodes and cannot forge a bare reference node.
