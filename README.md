# httk-core

![Status: Early beta](https://img.shields.io/badge/status-early--beta-orange)

> **⚠️ EARLY BETA**
>
> This is an early beta release of *httk₂*. The organization of the packages
> and their APIs should not yet be regarded as stable, and may change between
> releases.

`httk-core` is the central lightweight dependency shared by *httk₂* modules.

It provides:

- the `httk.core` package within the PEP 420 native `httk` namespace;
- shared view/backend and data-stream primitives; and
- plugin discovery and aggregate operations such as `httk.core.load`, to which
  other httk modules can register capabilities.
- the extensible `httk` executable, a lazy top-level command registry, and
  stdlib-backed Ed25519 signing.

Most users should install the [`httk2`](https://github.com/httk/httk2)
metapackage, which selects a useful set of httk modules:

```console
pip install httk2
```

Install only the core package with:

```console
pip install httk-core
```

Other distributions, such as `httk-atomistic`, install their own packages under the
same `httk` namespace and can then be imported as `httk.atomistic`.
