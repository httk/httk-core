# Views and Backends

This page explains a core *httk₂* design pattern used in `httk.core.datastream` and intended to generalize to other domains (for example, structures).
For detailed datastream usage and API-oriented examples, see {doc}`datastreams`.

## The Pattern

The pattern has three pieces:

- `XBackend`: internal carrier for one representation of data (`TextstreamFilename`, `TextstreamString`, `BytestreamBytes`, ...).
- `XView`: user-facing interface for *how you want to work with that data right now* (`TextstreamStringView`, `BytestreamFileView`, ...).
- `XLike`: union type accepted by API functions so callers can pass many natural inputs.

Typical flow inside a function:

1. Accept `XLike`.
2. Convert once to a specific view that matches your algorithm.
3. Write the algorithm only against that view.

This keeps APIs flexible for callers and keeps implementation logic simple and consistent.

## Why This Is Useful

Callers can use whichever representation they already have:

- a filename
- an open file object
- raw in-memory data (`str`, `bytes`)
- an existing backend or view

Function code still stays clean because it normalizes to a single view immediately.

## Concrete Example First: Datastreams

The first concrete use in `httk-core` is datastream normalization:

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

## Design Guidance

When introducing a new domain (`X`), keep these rules:

1. Define a clear `XLike` type for accepted inputs.
2. Keep `XBackend` focused on representation and state.
3. Keep `XView` focused on interface ergonomics.
4. In user-facing functions, normalize early (`xview = XSomeView(xlike)`).
5. Document ambiguity hints when one raw type can represent multiple meanings.

## Shared State and `unwrap`

Views of the same underlying backend share stream state:

- reading from one view advances position seen by another view on the same backend
- closing from one view closes the underlying stream for the others

`unwrap(obj)` is available when you need the most raw underlying representation that a backend/view can expose.
