# Views and Backends

This page explains a core *httk₂* design pattern used across *httk-core*: in Datastreams
({doc}`datastreams`) and Vectors ({doc}`vectors`), and in downstream domains such as structures.

## The Pattern

The pattern has three pieces:

- `X` or sometimes `XBackend`: internal carrier for one representation of data (`VectorFrac`, `VectorSurd`, `VectorNative`, `VectorNumpy`, `TextstreamFilename`, ...).
- `XView`: user-facing interface for *how you want to work with that data right now* (`VectorFracView`, `VectorSurdView`, `VectorNativeView`, `VectorNumpyView`, ...).
- `XLike`: union type accepted by API functions so callers can pass many natural inputs (`VectorLike`, `TextstreamLike`, ...).

Concrete backends are usually named `X`; only abstract family roots conventionally carry the
`Backend` suffix. The corresponding view and input-union names are
`XView` (`VectorFracView`, `VectorNumpyView`, ...) and `XLike` (`VectorLike`, `TextstreamLike`, ...).

Typical flow inside a function:

1. Accept `XLike`.
2. Convert once to a specific view that matches your algorithm.
3. Write the algorithm only against that view.
4. (Optional) convert into a View matching the type received.

This keeps APIs flexible for callers and keeps implementation logic simple and consistent.

## Why This Is Useful

Callers can use whichever representation they already have:

- a filename
- an open file object
- raw in-memory data (`str`, `bytes`)
- an existing backend or view

Function code still stays clean because it normalizes to a single view immediately.

## Concrete Example: Vectors

Vector APIs accept native sequences, exact vectors, and numpy views through `VectorLike`. A
function can do its work in the exact `VectorFracView`, then use `coerce()` to return the result in
the caller's kind:

```python
from httk.core import coerce
from httk.core.vectors import FracVector, VectorFracView, VectorLike


def center(vector: VectorLike) -> VectorLike:
    view = VectorFracView(vector)
    result = view - view[0]
    return coerce(FracVector.create(result), vector)
```

The same function can accept a `FracVector`, `VectorNativeView`, or `VectorNumpyView`; the final
line uses the received object as a prototype when choosing the return type.

## Concrete Example: Datastreams

Datastream normalization uses this pattern:

- text data:
  - `TextstreamLike` -> `Textstream...View` -> `Textstream...Backend`
- byte data:
  - `BytestreamLike` -> `Bytestream...View` -> `Bytestream...Backend`

In both cases, function authors can immediately normalize input into one view and then write logic against that one interface only.

```python
from httk.core import TextstreamFileView, TextstreamLike


def process_text(slike: TextstreamLike, **hints: object) -> list[str]:
    stream = TextstreamFileView(slike, **hints)
    return [line.strip() for line in stream]
```

## Generalization: Other Domains (Structures)

The same pattern applies to richer domains such as structures:

```python
from httk.atomistic import StructureLike, ASEAtomsView


def compute_bandpath(slike: StructureLike) -> list[tuple[float, float, float]]:
    atoms = ASEAtomsView(slike)
    # Algorithm only depends on the ASE Atoms view interface.
    cell = atoms.cell
    ...
```

`StructureLike` is the accepted input union, while `ASEAtomsView` is the normalized working interface.
As with datastreams, this lets callers pass many natural representations without complicating algorithm code.

Views are usually lazy: construction stores only the backend, and presentation state converts on
first access and is kept. Views where that is impossible — immutable builtin subclasses, external
mutable objects, or documented construction-time validation — stay eager.

## Design Guidance

When introducing a new domain (`X`), keep these rules:

1. Define a clear `XLike` type for accepted inputs.
2. Keep `XBackend` focused on representation and state.
3. Keep `XView` focused on interface ergonomics.
4. In user-facing functions, normalize early (`xview = XSomeView(xlike)`).
5. Document ambiguity hints when one raw type can represent multiple meanings.

## Shared State, `coerce`, and `unwrap`

Views of the same underlying backend share stream state:

- reading from one view advances position seen by another view on the same backend
- closing from one view closes the underlying stream for the others

`unwrap(obj)` is available when you need the most raw underlying representation that a backend/view can expose.

`coerce(value, target)` is the best-effort conversion path when an algorithm has produced one
representation but its caller's kind matters. A class target names the desired type; an instance
target acts as a prototype. The registry-backed coercers are described in {doc}`registry` under
{ref}`coercers`.
