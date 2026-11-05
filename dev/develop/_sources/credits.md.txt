# Citation credits

*httk₂* keeps a run-time registry of functionality actually used and lets the
user optionally print a citation list (`print(httk.core.credits)`). Print the
credits explicitly when a program finishes or produces a report:

```python
import httk.core

print(httk.core.credits)
```

The output explains what the running program ought to cite and why. Module
authors can register a `Reference` or a mapping accepted by
`Reference.create`:

```python
from httk.core import register_citation

register_citation(
    applies_to="Symmetry recognition uses spglib",
    references={"title": "The spglib library", "doi": "10.example/doi"},
)
```

For a one-function credit, use a cached helper so the citation registers once,
on first use of that function. This is the shape used by the symmetry
pathfinding code in *httk-atomistic*:

```python
from functools import cache

from httk.core import register_citation


@cache
def _register_pathfinding_citation() -> None:
    register_citation(
        applies_to="Symmetry pathfinding uses subgroup matching",
        references={"title": "Connecting Crystal Structures by Symmetry via Subgroup Matching"},
    )


def find_path(structure: object) -> None:
    _register_pathfinding_citation()
    ...
```

Registration calls belong in the feature modules that use the cited work, at
import or lazy-import sites. Do not put them in `httk.registry.*` registration
packages; those packages are imported eagerly during discovery and would
credit everything installed rather than what the program used.
