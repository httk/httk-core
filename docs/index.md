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
- **Views and backends**: {doc}`view_backend_pattern`
- **Module registry**: {doc}`registry`
- **Datastreams**: {doc}`datastreams`
- **Extensible CLI**: {doc}`cli`
- **Plugins**: {doc}`plugins`
- **Cryptography**: {doc}`crypto`
- **Operator identity**: {doc}`identity`
- **Projects and templates**: {doc}`projects`
- **Property definitions & entry providers**: {doc}`property_definitions`
- **Vectors**: {doc}`vectors`
- **Exact math on rationals and decimals**: {doc}`exactmath`
- **Citation credits**: {doc}`credits`
- **Runnable examples**: {doc}`examples/index`

The topic pages above are short and practical; each links onward to its full
guide in the **Details** section of the sidebar.
```

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

```python
from httk.core.vectors import FracVector, VectorNumpyView

cell = FracVector([["1/2", 0], [0, "1/3"]])
assert cell[0, 0] == 1 / 2
numeric = VectorNumpyView(cell)
assert numeric.tolist() == [[0.5, 0.0], [0.0, 1 / 3]]
print(numeric)
```

```{toctree}
:maxdepth: 2
:caption: Documentation

reference/index
view_backend_pattern
registry
datastreams
cli
plugins
crypto
identity
projects
property_definitions
vectors
exactmath
credits
examples/index
```

```{toctree}
:maxdepth: 1
:caption: Details

details/view_backend_pattern
details/registry
details/datastreams
details/plugins
details/property_definitions
details/vectors
details/exactmath
```
