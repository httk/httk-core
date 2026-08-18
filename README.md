# httk-core

![Status: Pre-release](https://img.shields.io/badge/status-pre--release-red)

> **⚠️ PRE-RELEASE**
>
> The version assigned to *httk-core* designates the overall version of *httk₂*,
> and thus starts at v2.0.0. However, versions v2.0.* are to be considered
> prereleases, and semantic versioning will not be used until v2.1.0.

`httk-core` is the central lightweight dependency shared by httk₂ modules.

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
