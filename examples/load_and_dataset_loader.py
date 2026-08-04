"""Getting data into httk: the `load` dispatcher and the `DatasetLoader`

*httk-core* offers two quite different doors into "read this data": a
**dispatcher** for file formats, and a **lazy dataset loader** for httk's own
JSON/JSON-LD data files. This example runs both, end to end, against files it
writes into a temporary directory, so it needs no network and no data package.

**`httk.core.load` — dispatch by file type.** `load("some/file.cif")` does not
itself know any file format. It resolves *which reader to call* and hands the
original filename over. Resolution has three steps, and they are worth knowing
because they explain what a format module has to register:

1. At most one recognized *compression* suffix is stripped off the name
   (`.gz`, `.bz2`, ...), giving an *inner* name. The reader still receives the
   original, still-compressed path — the datastream layer decompresses
   transparently when the reader opens it.
2. The inner name's *extension* is looked up in the extension registry
   (`.cif`, `.poscar`, ...).
3. Failing that, the inner name's *exact basename* is looked up, case
   insensitively, in a separate basename registry. This is how extension-less
   files such as `POSCAR` and `CONTCAR` dispatch at all.

*httk-core* ships **no** readers of its own — it is the contract
layer, not a format library. The registries are filled by sibling modules:
importing `httk.core` walks the `httk.registry` namespace package and imports
every handler package it finds there, and each of those calls
`httk.core.register.register_reader` to claim its extensions and basenames. So
what `known_extensions()` reports is a *statement about the installation*: with
only *httk-core* installed both registries are empty, and with *httk-io*
alongside it they list that module's formats. This example prints whichever is
the case here, then shows the explicit error `load` raises when
nothing matches — it names the file and lists everything that *is* registered,
which is usually the fastest way to notice a module is missing.

**`DatasetLoader` — httk's dataset files.** A `DatasetLoader` is a *declare-time
placeholder*: constructing one records its arguments and performs no I/O
whatsoever. The file is read the first time `.data`, `.meta`, or `.index` is
touched. That makes it cheap for a module to declare its reference datasets at
import time and pay for them only if someone actually uses them. Loaders that
share an `identifier` deduplicate: the first load wins and later loaders with
that identifier hand back the same object.

The file itself may be either shape:

- **Plain JSON** — any JSON value at all. It comes back as-is through `.data`,
  with `.meta` and `.index` both `None`.
- **Structured JSON-LD** — a document with `@context`, `@id`, `@type`, header
  fields, a `data` object and an optional `indicies` object. Then `.meta` is a
  `DatasetMeta` carrying the header, the per-dataset `@id`s and the per-field
  property URLs harvested from the context; `.data` and `.index` are
  `DatasetRecord` views whose top-level keys are reachable both as attributes
  (`data.spacegroups`) and as items (`data["spacegroups"]`).

Compression is invisible to all of this: `symmetry.json.gz` loads exactly like
`symmetry.json`, because the format is decided from the name *after* the
compression suffix is stripped.
"""

import gzip
import json
import tempfile
from pathlib import Path
from typing import Any

from httk.core import DatasetLoader, DatasetMeta, DatasetRecord, load
from httk.core.register import known_extensions, known_filenames

# A small JSON-LD dataset document: a context naming the dataset and its fields,
# a few header fields, the data itself, and a lookup index into it.
SYMMETRY_BASICS: dict[str, Any] = {
    "@context": {
        "@vocab": "https://example.org/vocab#",
        "data": {
            "@id": "https://example.org/symmetry_basics",
            "@context": {
                "spacegroups": {
                    "@id": "https://example.org/spacegroups",
                    "@context": {
                        "number": "https://example.org/number",
                        "hall": "https://example.org/hall",
                    },
                },
            },
        },
    },
    "@id": "https://example.org/symmetry_basics",
    "@type": "Dataset",
    "title": "Symmetry basics",
    "creator": "httk AUTHORS",
    "license": "CC0",
    "data": {
        "spacegroups": [
            {"number": 1, "symbol": "P1", "hall": {"symbol": "P 1"}},
            {"number": 2, "symbol": "P-1", "hall": {"symbol": "-P 1"}},
        ]
    },
    "indicies": {"by_number": {"1": 0, "2": 1}},
}


def show_load_dispatch() -> None:
    """What `httk.core.load` can currently dispatch, and how it fails."""
    print("== httk.core.load: the reader registries ==")
    print("known extensions:", known_extensions() or "(none registered)")
    print("known filenames: ", known_filenames() or "(none registered)")
    print("httk-core itself registers none of these; every entry above was contributed")
    print("by a sibling module discovered through the httk.registry namespace package.")

    mystery = "/some/dir/mystery.notaformat"
    try:
        load(mystery)
    except ValueError as exc:
        print(f"load({mystery!r}) ->", type(exc).__name__)
        print("   ", exc)
    print()


def show_plain_json(directory: Path) -> None:
    """Plain JSON: whatever the file contains, verbatim, with no meta or index."""
    print("== DatasetLoader: plain JSON ==")
    path = directory / "plain.json"
    path.write_text(json.dumps({"a": 1, "b": [2, 3]}), encoding="utf-8")

    loader = DatasetLoader("example_plain", path)  # no I/O yet
    print("declared loader for", path.name, "- nothing read so far")
    print("data: ", loader.data)  # this line is what triggers the read
    print("meta: ", loader.meta)
    print("index:", loader.index)
    print()


def show_structured_json(directory: Path) -> None:
    """Structured JSON-LD: header metadata, datasets and indices."""
    print("== DatasetLoader: structured JSON-LD ==")
    path = directory / "symmetry.json"
    path.write_text(json.dumps(SYMMETRY_BASICS), encoding="utf-8")

    loader = DatasetLoader("example_symmetry", path)

    meta = loader.meta
    assert isinstance(meta, DatasetMeta)
    print("meta.id:         ", meta.id)
    print("meta.type_:      ", meta.type_)
    print("meta.header:     ", meta.header)
    print("meta.dataset_ids:", meta.dataset_ids)
    print("meta.fields:     ", meta.fields)

    data = loader.data
    assert isinstance(data, DatasetRecord)
    print("data keys:       ", list(data.keys()))
    for entry in data.spacegroups:  # attribute access ...
        print(f"  spacegroup {entry['number']}: {entry['symbol']} (Hall {entry['hall']['symbol']})")
    print("data['spacegroups'] is data.spacegroups:", data["spacegroups"] is data.spacegroups)

    index = loader.index
    assert isinstance(index, DatasetRecord)
    row = index.by_number["2"]
    print("index.by_number['2'] ->", row, "->", data.spacegroups[row]["symbol"])
    print()


def show_compression_and_dedup(directory: Path) -> None:
    """`.json.gz` loads like `.json`; a repeated identifier reuses the first load."""
    print("== DatasetLoader: transparent compression and identifier dedup ==")
    path = directory / "symmetry.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(SYMMETRY_BASICS, handle)

    gzipped = DatasetLoader("example_symmetry_gz", path)
    print(path.name, "-> first spacegroup:", gzipped.data.spacegroups[0]["symbol"])

    # The same identifier as the .gz loader above, but a source that does not
    # exist: the earlier result is handed back and the bogus source is ignored.
    again = DatasetLoader("example_symmetry_gz", "/no/such/file.json")
    print("same identifier reuses the first load:", again.data is gzipped.data)

    # A file:// URL string is recognized as a URL without any kind= hint.
    via_url = DatasetLoader("example_symmetry_url", (directory / "symmetry.json").as_uri())
    print("loaded via file:// URL:", via_url.data.spacegroups[1]["symbol"])
    print()


def main() -> None:
    show_load_dispatch()
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        show_plain_json(directory)
        show_structured_json(directory)
        show_compression_and_dedup(directory)


if __name__ == "__main__":
    main()
