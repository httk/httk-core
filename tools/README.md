# Verify a release locally

Run this standalone checker with Python 3.12+ before tagging any of the six
runtime distributions. It needs Git, make, network access to PyPI and published
dependency docs, and Node/npm for repositories with a package lock.

From a module directory in the workspace:

```console
make docs-lock
make docs-inventories
python -m httk.core.docs check-release --tag v2.1.0
# Review and commit the intended release changes, including generated inputs.
python ../httk-core/tools/check_release.py . --tag v2.1.0
```

For core itself, use `python tools/check_release.py . --tag v2.1.0`.
The checker comes from the core **checkout**; it needs no new published core
version and may also be copied and run as a standalone file. It accepts any
module repository path. The tag defaults to `v` plus `project.version`.

The checker refuses uncommitted files and exports the exact HEAD commit into
a new temporary directory. Ignored build artifacts, the active virtual
environment, and sibling source checkouts do not enter the snapshot. Gitlinks
are rejected: this checks individual distributions, not aggregate websites.

It then performs these gates, stopping on the first failure:

1. Create a fresh venv and install only `.[dev]` from the snapshot, resolving
   dependencies from PyPI. Install JavaScript dependencies with `npm ci` when
   a package lock exists. Run `pip check` and `make ci`.
2. Add `.[dev,docs,release]`, repeat dependency validation, check the release
   tag/lock/inventories, and run `HTTK_DOCS_VERSION=<tag> make release-check`.
   CI runs again because the release environment has different dependencies.
3. Run `make docs-lock-check`, including its separate locked-docs environment.
4. Install the built wheel without extras in another fresh venv, check its
   dependencies and version, and import the primary package and the public
   roots declared in `docs/versioning.toml`, outside the source tree.

The separate dev phase matters: docs tools can incidentally install a package
that ordinary CI forgot to declare. Likewise, local workspace type-checker
paths can hide missing package requirements even when a venv looks fresh.

The printed output directory retains full per-gate logs, dependency versions,
environments, and `source/dist/` artifacts on success or failure. `report.json`
records the result, exact commit, checker hash, and artifact hashes. Use
`--output-dir /absolute/new/directory` to choose its location; an existing
directory is refused. Remove it yourself when no longer needed.

A pass applies to that commit and the dependencies recorded in the logs.
It is not a container or a reproduction of GitHub's operating-system image.
Browser checks and external database services remain separate gates when
required; optional test skips remain visible in the logs. The checker does
not refresh inventories, modify the working checkout, sign, tag, or publish.

After a pass, sign/tag/push the verified source. Re-run if its source changes.
