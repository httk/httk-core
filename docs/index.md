# *httk-core*

This site documents specifically the *httk-core* module. For the full
documentation of *httk₂* as a whole, see [docs.httk.org](https://docs.httk.org).

*httk-core* is a thin module providing core functionality for *httk₂*.

It also defines the neutral `httk.core.EntryProvider` contract and its registry
(`register_entry_provider`), by which domain modules supply described, queryable
entry types to consumers such as *httk-serve* without either side depending
on the other.

```{admonition} Quick links
:class: tip

- **API reference**: {doc}`reference/index`
- **Views and backends guide**: {doc}`view_backend_pattern`
- **Datastream guide**: {doc}`datastreams`
- **Extensible CLI and Ed25519 signing**: {doc}`cli_and_signing`
- **Projects and the anchor**: {doc}`project_anchor`
- **OPTIMADE definitions & entry providers**: {doc}`optimade_definitions`
- **Exact math on rationals and decimals**: {doc}`exactmath`
- **Vectors guide**: {doc}`vectors`
- **Runnable examples**: {doc}`examples/index`
````

## Install

Preferably work in a Python virtual environment, then do:
```bash
git clone https://github.com/httk/httk-core
cd httk-core
python -m pip install -e .
```

## Usage (tiny example)

The main subpackages are `httk.core.datastream`, `httk.core.optimade`,
`httk.core.storage`, `httk.core.vectors`, and `httk.core.views`.

```{toctree}
:maxdepth: 2
:caption: Documentation

reference/index
view_backend_pattern
datastreams
cli_and_signing
project_anchor
optimade_definitions
vectors
exactmath
examples/index
```
