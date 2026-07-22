# httk-core

`httk-core` is the central lightweight dependency shared by httk v2 modules.
It provides:

- the `httk.core` package within the PEP 420 native `httk` namespace;
- shared view/backend and data-stream primitives; and
- plugin discovery and aggregate operations such as `httk.core.load`, to which
  other httk modules can register handlers.

Most users should install the [`httk2`](https://github.com/httk/httk2)
metapackage, which selects a useful set of httk modules:

```console
pip install httk2
```

Install only the core package with:

```console
pip install httk-core
```

Other distributions, such as `httk-io`, install their own packages under the
same `httk` namespace and can then be imported as `httk.io`.

Development and release instructions are in the
[`RELEASING.md`](https://github.com/httk/httk-core/blob/main/RELEASING.md)
guide.
