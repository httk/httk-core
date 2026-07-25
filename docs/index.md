# *httk-core*

This site documents specifically the *httk-core* module. For the full
documentation of *httk₂* as a whole, see [docs.httk.org](https://docs.httk.org).

*httk-core* is a thin module providing core functionality for *httk₂*.

It also defines the neutral `httk.core.EntryProvider` contract and its registry
(`register_entry_provider`), by which domain modules supply described, queryable
entry types to consumers such as *httk-optimade* without either side depending
on the other.

```{admonition} Quick links
:class: tip

- **API reference**: {doc}`reference/index`
- **Views and backends guide**: {doc}`view_backend_pattern`
- **Datastream guide**: {doc}`datastreams`
- **OPTIMADE definitions & entry providers**: {doc}`optimade_definitions`
- **Exact math on rationals and decimals**: {doc}`exactmath`
- **Vectors guide**: {doc}`vectors`
- **Runnable examples**: {doc}`examples/index`
- **Examples notebook**: {doc}`notebooks/examples`
````

## Install

Preferably work in a Python virtual environment, then do:
```bash
git clone https://github.com/httk/httk-core
cd httk-core
python -m pip install -e .
```

## Usage (tiny example)

```python
from httk.core import subpackages

print(subpackages)
```

```{toctree}
:maxdepth: 2
:caption: Documentation

reference/index
view_backend_pattern
datastreams
optimade_definitions
vectors
exactmath
examples/index
notebooks/examples
```
