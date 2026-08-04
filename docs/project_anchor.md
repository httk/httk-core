# Projects and the anchor

A *project* is to a campaign what a Git repository is to a source tree: a
directory marked, at its root, by a small control directory that every command
discovers by walking upward from wherever it is run. In *httk* that directory is
`httk_project` and its versioned manifest is `project.json`.

The anchor lives in `httk.core.project`, so a *httk-core* installation has working
projects on its own. Capabilities that build on a project — *httk-workflow*
adds a workflow workspace, signed manifests, a doctor, and remotes — layer on
top of the anchor without the anchor depending on them.

## The command line

Installing *httk-core* provides `httk project`, modeled on `git init`:

```console
httk project init                 # make the working directory a project
httk project init PATH --name X   # or make PATH one, with an explicit name
httk project show                 # describe the nearest project
httk project show --json          # the same, machine-readable
```

`httk project init` refuses a directory that is already a project, exactly as
`git init` refuses nothing but the anchor here is a hard error rather than a
re-initialization. It creates only the anchor: `project.json`, the project's
Ed25519 signing key under `httk_project/keys/`, and a `remotes/` directory. It
creates no workflow workspace; a workflow installation adds that.

`httk project show` describes the anchor — its metadata, whether it pins a key
and which.

## Discovering and reading a project

```python
from httk.core.project import discover_project, read_project, require_project

root = discover_project()          # the nearest project at or above the cwd, or None
root = require_project()           # the same, but raises when there is none
metadata = read_project(root)      # validated project.json as a dict
```

`initialize_project` creates the anchor; `import_v1_project` creates one from a
legacy *httk* v1 `ht.project` directory, adopting the identities its old
manifests were signed with:

```python
from httk.core.project import initialize_project

metadata = initialize_project("campaign", name="My campaign")
```

## Identity keys, pinning, and trust

A project owns one Ed25519 signing key, built on {doc}`cli_and_signing`'s
`httk.core.crypto`. Its public half is recorded in `project.json` and is the
trust anchor a signed manifest is checked against — never the key a manifest
carries in its own header.

```python
from httk.core.project import (
    pin_project_key,        # adopt keys/project.pub as the trust anchor
    trust_project_key,      # adopt one further public key as an anchor
    pinned_project_key,     # the project's own pinned key, or None
    trusted_project_keys,   # every anchor: the pinned key and any adopted one
    key_fingerprint,        # the stable sha256: display fingerprint of a key
)
```

Public keys are written as `ed25519:BASE64`; `format_public_key`,
`parse_public_key`, `canonical_public_key`, and `read_public_key_file` convert
between that spelling, the raw 32 bytes, and a `*.pub` file.
