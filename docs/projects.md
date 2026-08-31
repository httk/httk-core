# Projects

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

The core-owned `httk project` command has five subcommands:
`init`, `show`, `import-v1`, `export`, and `verify-export`.

```console
httk project init [--description TEXT] PATH...
httk project init --name NAME --description TEXT PATH
httk project show [PATH...]
httk project show --json PATH...
httk project import-v1 PATH...
httk project import-v1 --source DIR --name NAME PATH
httk project export OUT.ZIP
httk project verify-export [--expect-key FINGERPRINT] [--trusted-key FINGERPRINT ...] ZIP...
```

`init` makes each `PATH` a project. At least one path is required. `--name`
is available when initializing one path and defaults to its directory name;
`--description` defaults to an empty string. It refuses an existing project and creates
`httk_project/project.json`, the project's Ed25519 key under
`httk_project/keys/`, and `httk_project/remotes/`. It creates no workflow
workspace. To populate a new project from a plugin or an explicit template,
use `httk project init --template`; see the Project templates section below.

`show` describes the nearest project when no path is supplied, or each named
project. Human output is target-delimited and `--json` always emits an array.
`import-v1` imports each legacy v1 project in
`PATH/ht.project` by default; `--source DIR` selects another v1 directory.

`export` packages the nearest project tree into a signed redistribution ZIP,
excluding the private key, and signs it with the project's Ed25519 key.
`verify-export` checks such a ZIP and prints the signer's public key and
fingerprint; `--expect-key` requires a specific signer fingerprint and
`--trusted-key` (repeatable) supplies fingerprints to trust. The programmatic
equivalents are `export_project` and `verify_export` in `httk.core.project`.

Root options are processed before command dispatch. `-C DIR` changes directory
first, so any *httk* command can target a project from elsewhere:

```console
httk -C ~/proj project show
httk -C ~/proj project show --json
```

See {doc}`cli` for the root command-line rules. The `httk project` namespace
belongs to *httk-core*, which owns every verb on it: `init | show | import-v1 |
export | verify-export` for the anchor, and `doctor | manifest | seal | unseal |
verify-seal` for checking and pinning the tree (see {doc}`sealing`).

(project-members)=

## Project members

A project can hold *members*: self-contained subtrees whose internals another
module owns — a workflow workspace is the first one. Core owns the verbs; a
member only teaches core how to treat its own subtree. Three pieces cooperate:

- **A module registers a kind.** `register_project_member_kind(kind, handler)`
  (from `httk.core`) records a lazy `"module:callable"` reference that resolves
  to an object implementing `ProjectMemberHandler` — the methods core drives:
  `manifest_exclusions`, `guard`, `seal_digest`, `verify`, `doctor`, and the
  optional `scan_project`. (A member seals through its own module; core only
  records the resulting digest.)
- **A project records its members.** `register_project_member(project_root,
  path, kind, *, name=None)` writes `httk_project/members.json`, mapping a
  subtree path to its kind and an optional recorded `name` (member names, when
  set, are unique within a project). Registration is refused while the project
  is sealed. `project_members` reads them back; `set_project_member_name` sets
  or clears a member's name.
- **Core drives the verbs.** `httk project seal`, `manifest`, `doctor`, and
  `verify-seal` hand each registered member's subtree to its handler and fold the
  results into one project-wide answer — a project seal records each member's own
  seal digest, so it transitively pins whole subtrees without re-hashing them.

A member whose kind no module has installed is reported clearly rather than
silently skipped: sealing refuses it, and `doctor` and `verify-seal` flag it.

`httk project adopt` (re)establishes each member's machine-local links on the
current machine — the per-user or machine-local bindings a member needs to be
usable here, such as httk-workflow registering the member's workspace in the
per-user name registry under its recorded name. Adoption is idempotent and never
touches sealed state; a member whose handler defines no adopt hook is simply
skipped, and adopting a project with no such members is a no-op.

## Project templates

An *httk₂* project template supplies files and, optionally, a hook that
generates more project content. Templates can be bundled by plugins or used
directly from a directory containing `httk_project_template.toml`.

Install a plugin, then initialize a project from one of its templates:

```console
httk plugin install ./my-plugin
httk project init --template my-plugin:starter --parameter n=3 my-project
```

List installed templates and their plugin-qualified selectors with:

```console
httk project init --list-templates
```

An explicit template directory works without a plugin:

```console
httk project init --template ./templates/starter my-project
```

Templates can also be selected by a bare template ID when exactly one
installed template has that ID; a bare ID shared by multiple plugins is
ambiguous and must be qualified.

### The `httk_project_template.toml` manifest

The manifest is strict: its only top-level table is `[template]`, and unknown
keys are errors.

```toml
[template]
id = "starter"
description = "A small starter project"
files = ["README.md", "src"]

[template.instantiate]
file = "instantiate.py"

[template.parameters.name]
type = "string"
description = "Project display name"

[template.parameters.count]
type = "integer"
default = 1
```

#### `[template]`

`id` is required and must match `[a-z0-9._-]+`; it must not be `.` or `..`,
and must not start with `-`. `description` is an optional string.

`files` is an optional array of relative POSIX members. Each member may be a
regular file or a directory. Members must remain below the template root,
must not be absolute, contain empty components, `.`, or `..`, or traverse a
symlink. They must be unique and may not overlap by containment. The manifest
itself, `httk_project_template.toml`, and the instantiate hook may not be
listed. Directory members are copied recursively; symlinks and special files
inside them are rejected during instantiation.

#### `[template.instantiate]`

The table is optional and accepts the required `file` key. A `.py` file is run
with the current Python interpreter. A non-Python file must be an executable
regular member. The hook is required when the template declares any
parameters.

#### `[template.parameters.<name>]`

Parameter names must match `[A-Za-z_][A-Za-z0-9_]*`. Each parameter table
accepts:

- `type`, required and one of `string`, `number`, `integer`, `boolean`,
  `array`, or `object`;
- `description`, an optional string;
- `default`, an optional JSON-compatible value matching `type`.

A parameter with no `default` is mandatory. A parameter with a default is
optional and receives that default when it is not supplied. `number` accepts
integers and floating-point numbers but not booleans; `integer` also excludes
booleans. `array` and `object` mean JSON arrays and objects.

Parameters are supplied by repeating `--parameter NAME=VALUE`. `VALUE` is
parsed as JSON when possible and is otherwise treated as a literal string.
Quote a literal string as JSON, for example:

```console
httk project init --template starter \
  --parameter name='"Ada"' --parameter count=3 --parameter enabled=true demo
```

The quotes around `"Ada"` are needed because an unquoted `Ada` is the JSON
fallback string, while a value such as `3` is parsed as an integer. Unknown
parameters, missing mandatory parameters, and values of the wrong type fail
before the project directory is created.

### The instantiate hook

The hook receives one JSON request on standard input. It runs with the project
directory as its current working directory (`cwd`) and with the selected
template files already copied. The request envelope is:

```json
{
  "format": "httk-project-template-instantiate",
  "format_version": 2,
  "template": "starter",
  "parameters": {"name": "Ada", "count": 1},
  "project": {
    "name": "demo",
    "description": "",
    "project_id": "...",
    "root": "/absolute/path/to/demo"
  }
}
```

The `project` object contains the project information supplied by the caller,
plus `root`, which is the absolute project root. The `httk project init`
command supplies `name`, `description`, and `project_id`.

The hook inherits the environment except that variables beginning with
`HTTK_` are removed. `HTTK_CONFIG_HOME` and `HTTK_DATA_HOME` are retained.
The default hook timeout is 3600 seconds. A Python hook is invoked as
`sys.executable HOOK.py`; another hook is executed directly.

Write one JSON object to standard output. `{}` is the empty response. The
optional `notes` member must be an array of strings; those notes are printed
after initialization. Other response members are accepted but ignored by the
core. Nonzero exit status, invalid JSON, invalid notes, or a timeout fails
instantiation.

The `template_instantiate_main` helper validates the request envelope and
writes the response for a Python hook. A minimal hook is:

```python
from httk.core.project.templates import TemplateInstantiateRequest, template_instantiate_main


def handle(request: TemplateInstantiateRequest) -> dict[str, object]:
    with open("created.txt", "w", encoding="utf-8") as output:
        output.write(str(request.parameters["name"]))
    return {"notes": ["created project file"]}


template_instantiate_main(handle)
```

Returning `None` writes `{}`. Exceptions are reported as hook failure.

### Instantiation and rollback

`httk project init --template` performs the following sequence:

1. Resolve and validate the template, then validate parameters and apply
   defaults.
2. Create the project anchor.
3. Preflight destination collisions and copy the declared files and
   directories.
4. Run the optional instantiate hook.

Copying preserves file modes. Existing project members cause a collision
error, and the copy preflight prevents a partial copy from that error. Hook
changes are not transactional. If the target directory was fresh, any
failure removes it. If the target directory already contained entries, the
anchor and any copied or hook-created files remain and the command reports
that partial state.

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
