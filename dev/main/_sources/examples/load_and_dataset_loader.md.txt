# Getting data into httk: the `load` dispatcher and the `DatasetLoader`

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
only *httk-core* installed both registries are empty, and with *httk-atomistic*
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
  `DatasetLoaderRecord` views whose top-level keys are reachable both as attributes
  (`data.spacegroups`) and as items (`data["spacegroups"]`).

Compression is invisible to all of this: `symmetry.json.gz` loads exactly like
`symmetry.json`, because the format is decided from the name *after* the
compression suffix is stripped.

```{literalinclude} ../../examples/load_and_dataset_loader.py
:language: python
:lines: 58-
```
