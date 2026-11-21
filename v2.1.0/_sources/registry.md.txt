# Module registry

Capability modules extend *httk₂* by shipping small registration packages
under the reserved `httk.registry.<tier>.<module>` namespaces (`cli`,
`entries`, `io`, `schemas`). Discovery imports them eagerly at
`import httk.core`; they record **lazy references** (`"module:callable"`), so
nothing heavy loads until first use.

The registry you will meet first is the reader registry behind
`httk.core.load`, which dispatches on file extension or exact basename
(case-insensitively, with transparent decompression):

```python
from httk.core import load, register_reader

register_reader(
    name="demo",
    reader="example_package.readers:read_demo",
    extensions=(".demo",),
    filenames=("DEMOCAR",),
)
load("sample.demo.gz")   # decompressed, then dispatched to read_demo
```

The same shape repeats across the system — register with a lazy reference,
consume through a neutral entry point:

- **readers / writers** and **format adapters/serializers** (`load`, `save`);
- **entry providers, records, and families** — described, queryable data for storage and serving;
- **schema definition resources** — vendored OPTIMADE definition documents;
- **CLI commands**, **definition prefixes**, **compression codecs**,
  **leaf codecs**, **coercers**, and **canonical encoders** (content
  addressing, including canonical format v2).

For each registry's exact API, matching rules, save semantics, and the
discovery contract, see {doc}`details/registry`.
