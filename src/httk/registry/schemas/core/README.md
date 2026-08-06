# Vendored entry-type definitions

This directory holds the authoritative, supported copies of the OPTIMADE
standard *entry-type definition* documents that *httk-core* serves. Each JSON
file embeds the complete property definitions for one entry type (their
canonical `$id`s, types, units, requirements, and descriptions).

The checked-in files are the source of truth: httk-core supports exactly these
versions. They register as IRI-keyed schemas when `httk.core` is imported and
are loaded by `standard_entry_type` (packaged through `pyproject.toml`'s
`package-data` entry for `httk.registry.schemas.core`).

## Provenance

Source repository: <https://github.com/Materials-Consortia/schemas>

Fetched from:

| File | Version | Source URL |
| --- | --- | --- |
| `references.json` | v1.2 (30 properties) | <https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/references.json> |
| `files.json` | v1.2 (16 properties) | <https://schemas.optimade.org/defs/v1.2/entrytypes/optimade/files.json> |
| `calculations.json` | v1.3 (4 properties) | <https://schemas.optimade.org/defs/v1.3/entrytypes/optimade/calculations.json> |

(The `structures` standard is vendored by *httk-atomistic*, not here.)

## httk-authored entry types

These definitions were authored by httk and built from the local
`schemas-scource` output. Publication to <https://schemas.httk.org> is pending.
The vendored copies are authoritative until then and are refreshed by
re-copying from the build output.

| File | Identity IRI | Source | License |
| --- | --- | --- | --- |
| `runs.json` | `https://schemas.httk.org/defs/v0.1/entrytypes/runs` | `schemas-scource/output/defs/v0.1/entrytypes/runs.json` | [`LICENSE.httk`](./LICENSE.httk) |
| `records.json` | `https://schemas.httk.org/defs/v0.1/entrytypes/records` | `schemas-scource/output/defs/v0.1/entrytypes/records.json` | [`LICENSE.httk`](./LICENSE.httk) |

## License

The three Materials-Consortia definitions above are distributed under the MIT
License; see the adjacent [`LICENSE`](./LICENSE) file, fetched from
<https://raw.githubusercontent.com/Materials-Consortia/schemas/master/LICENSE>.
The httk-authored definitions are distributed under the MIT License; see
[`LICENSE.httk`](./LICENSE.httk).

## Refreshing

Run `make optimade-defs` from the repository root to re-fetch the three
Materials-Consortia files (and the `LICENSE`) from the URLs above. Refresh the
httk-authored files by re-copying `runs.json` and `records.json` from the local
`schemas-scource/output/defs/v0.1/entrytypes/` build output. These are source
tasks; ordinary builds and tests read the committed copies offline. After a
refresh, review the diff and re-commit only intended version changes.
