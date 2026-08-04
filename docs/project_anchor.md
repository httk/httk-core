# Projects and the anchor

A *project* is to a campaign what a Git repository is to a source tree: a
directory marked at its root by a control directory that commands discover by
walking upward from wherever they are run. In *httk* that directory is the
visible, deliberately non-hidden `httk_project/`; its versioned manifest is
`httk_project/project.json`. The Git analogy describes discovery, not naming:
the anchor is visible so it is easy to inspect and manage.

The anchor lives in `httk.core.project`, so an *httk-core* installation has a
working project on its own. Capability modules layer their own project data on
top of the anchor without making the anchor depend on them.

## The command line

The core-owned `httk project` command has exactly three subcommands:
`init`, `show`, and `import-v1`.

```console
httk project init
httk project init PATH --name NAME --description TEXT
httk project show
httk project show PATH --json
httk project import-v1 PATH
httk project import-v1 PATH --source DIR --name NAME
```

`init` makes `PATH` a project, or uses the current directory when `PATH` is
omitted. `--name` defaults to the directory name and `--description` defaults
to an empty string. It refuses an existing project and creates
`httk_project/project.json`, the project's Ed25519 key under
`httk_project/keys/`, and `httk_project/remotes/`. It creates no workflow
workspace.

`show` describes the nearest project, or the project named by `PATH`.
`--json` emits one machine-readable document. `import-v1` imports the legacy v1 project in
`PATH/ht.project` by default; `--source DIR` selects another v1 directory.

Root options are processed before command dispatch. `-C DIR` changes directory
first, so any *httk* command can target a project from elsewhere:

```console
httk -C ~/proj project show
httk -C ~/proj project show --json
```

See {doc}`cli` for the root command-line rules. The `httk project` namespace
belongs to *httk-core*; modules provide their own namespaces, for example
`httk workflow project ...`. There is no project-subcommand extension
mechanism.

## Discovering and reading a project

```python
from httk.core.project import discover_project, read_project, require_project

root = discover_project()       # nearest project, or None
root = require_project()        # nearest project, or an error
metadata = read_project(root)   # validated httk_project/project.json
```

`discover_project(start)` resolves `start` and checks it and each parent for
`httk_project/project.json`. It returns the project root as a `Path`, or
`None`; `require_project(start)` has the same behavior but raises when no
project exists. Both refuse legacy project directories; see
the Legacy project directories section below.

## Initializing and importing

The API equivalents of the two creating commands are
`initialize_project` and `import_v1_project`:

```python
from httk.core.project import import_v1_project, initialize_project

metadata = initialize_project("campaign", name="My campaign")
metadata = import_v1_project("campaign", name="My campaign")
```

`initialize_project` creates only the anchor, its `project.json`, its Ed25519
key, and its `remotes/` directory. `import_v1_project` reads the v1
`ht.project/config`, copies its public-key files into
`httk_project/keys/legacy-public/`, records the source, and makes readable
legacy keys trusted. It also creates the new project's own key and pins it in
`httk_project/project.json`; queue data is not imported by this function.

## Legacy project directories

Discovery refuses a legacy directory by raising
{class}`httk.core.project.LegacyProjectError`. The refusal includes the
remedy.

A v1 project containing `ht.project` produces:

```console
$ httk project show
httk project: found an httk v1 project ('ht.project') at /path/to/project; create the httk v2 anchor with: httk project import-v1 /path/to/project
```

Run the shown `httk project import-v1 /path/to/project`. It reads
`/path/to/project/ht.project/config`, copies the public keys, pins the readable
legacy keys as trusted, and creates `/path/to/project/httk_project/`.

A pre-release v2 project containing `.httk-project/project.json` produces:

```console
$ httk project show
httk project: found a project anchor from a pre-release httk v2 ('.httk-project') at /path/to/project; rename it: mv /path/to/project/.httk-project /path/to/project/httk_project
```

Apply the shown remedy from the project root:

```console
mv .httk-project httk_project
```

## Identity keys, pinning, and trust

A project owns one Ed25519 signing key. Its public half is recorded in
`httk_project/project.json` as `public_key` and is the trust anchor against
which a signed manifest is checked; verification does not trust a key merely
because a manifest carries it in its own header.

```python
from httk.core.project import (
    pin_project_key,        # pin httk_project/keys/project.pub
    trust_project_key,      # adopt another public key
    pinned_project_key,     # the project's pinned key, or None
    trusted_project_keys,   # the pinned key and adopted keys
    key_fingerprint,        # stable sha256: display fingerprint
)
```

`pin_project_key(root)` explicitly adopts the current
`httk_project/keys/project.pub` as the project's pinned trust anchor.
`trust_project_key(root, key)` adds another public key to `trusted_keys`.
`pinned_project_key(metadata)` reads the project's own pin, while
`trusted_project_keys(metadata)` returns it together with adopted keys.

Public keys are recorded as `ed25519:BASE64`.
`format_public_key`, `parse_public_key`, `canonical_public_key`, and
`read_public_key_file` convert between that spelling, raw 32-byte keys, and
`*.pub` files. `project_public_key_path(root)` returns the path to the
project's public key.
