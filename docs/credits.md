# Citation credits

`httk.core` tracks citations as the modules that use them are imported. Print
the credits explicitly when a program finishes or produces a report:

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

Registration is import-tracked: a credit appears only when the code path that
registers it has been imported or executed. Registration calls belong in the
feature modules that use the cited work, at import or lazy-import sites. Do
not put them in `httk.registry.*` registration packages; those packages are
imported eagerly during discovery and would credit everything installed rather
than what the program used.
