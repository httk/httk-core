# Plugins in detail

The `httk plugin` command installs a plugin directory as one managed unit.
Plugins can provide project templates, workflow packages, and executable
utility programs. The package root must contain `httk_plugin.toml`.

## The `httk_plugin.toml` manifest

The manifest is strict: its only top-level table is `[plugin]`, and unknown
keys are errors. A complete manifest can look like this:

```toml
[plugin]
name = "example-tools"
description = "Templates and command-line tools"
templates = ["templates/starter"]
workflows = ["workflows/example"]

[plugin.programs.example-tool]
file = "bin/example-tool"
description = "Run the example tool"

[plugin.build]
command = "sh build.sh"
platform = "uname -m"
artifacts = ["bin/example-tool"]
```

### `[plugin]`

`name` is required. It must match `[a-z0-9._-]+`, must not be `.` or `..`, and
must not start with `-`. The same rule applies to program names in
`[plugin.programs.<name>]`.

`description` is an optional string.

`templates` and `workflows` are optional arrays of relative POSIX directory
members. A template directory must contain a regular, non-symlink
`httk_project_template.toml`; a workflow directory must contain a regular,
non-symlink `httk_workflow.toml`. Members must stay below the plugin root, may
not contain absolute paths, empty components, `.` or `..`, and may not be
duplicates. Template and workflow directories may not overlap, including by
containment.

### `[plugin.programs.<name>]`

Each program table accepts:

- `file`, a relative POSIX member path below the plugin root. It must be a
  regular file, not a symlink or a path through a symlink.
- `description`, an optional string.

Without a build table, `file` must already exist when the manifest is parsed.
With a build table, it may be absent only when its path is covered by one of
the build `artifacts` patterns; the build must create it as a regular
executable file. A program is not published until it is executable.

### `[plugin.build]`

The build table is optional and uses the shared build vocabulary:

- `command` is a required nonempty command string. It is split into shell
  words; it is not run through a shell by the installer. A command such as
  `sh build.sh` can invoke a shell script.
- `platform` is an optional nonempty platform-probe command, also split into
  shell words. Its output is recorded and used to tag the build; when absent,
  the platform tag is `any`.
- `artifacts` is a required nonempty array of glob patterns. Each pattern is a
  nonempty relative POSIX pattern with no backslashes, `.` or `..` path
  components. Patterns may not match `httk_plugin.toml`.

The build command runs in the installed plugin directory. It must produce at
least one regular, non-symlink file matching the declared patterns. Declared
program files covered by those patterns are the deferred-existence case above.
The build inherits the environment except that `HTTK_*` variables are removed;
`HTTK_CONFIG_HOME` and `HTTK_DATA_HOME` are retained.

## Installing and replacing

Installation acquires the source into a staging directory. Directory sources
are copied; archives are safely extracted; archive URLs are downloaded; and
Git sources are cloned without retaining `.git`. A single top-level directory
from an archive or clone is unwrapped when it contains the plugin manifest.
Git source URLs use `git+http://`, `git+https://`, or `git+file://`; SSH
shorthand and `git+ssh://` are rejected. A ref after `@` is checked out, and
the resolved commit is recorded.

The installer validates the plugin manifest and fully validates every bundled
project-template manifest while the source is still staged. It then checks the
destination name and program-shim collisions before placing anything under
`plugins/<name>/`. With `--force`, an existing plugin of that name is moved
aside, its owned shims are removed, and the replacement is placed atomically.
The old installation is restored if placement fails.

The build, if any, runs after placement. A failed build does not undo the
installation: the plugin remains installed with `built` set to `false`, and
any shims from that failed build are removed. The command reports the remedy:

```console
httk plugin build NAME
```

`httk plugin build NAME` reruns the declared build and republishes its
programs. A plugin without a build table has `built = null` in its metadata;
its declared programs are checked and shimmed directly during installation.

## Installed layout and provenance

Installed plugins live below `data_home()/plugins`:

```text
data_home()/plugins/<name>/
    httk_plugin.toml
    plugin.json
    ... plugin members ...
```

`plugin.json` contains the installation format fields `format` (which is
`httk-plugin-install`), `format_version` (`2`), `name`, `source`,
`source_kind` (`directory`, `archive`, `url`, or `git`), `source_sha256`,
`installed_at`, `built`, `programs`, and
`shims`. Archive and URL sources also contain `archive_sha256`. Git sources
contain `ref` when one was supplied and the resolved `commit`.

`source_sha256` is the tree digest recorded before `plugin.json`, build output,
or the build log are added. After a successful build, `plugin.json` also
contains `built_at`, `platform_tag`, and `platform_output`. A build failure
clears those success fields and records `built = false`.

## Programs and shims

Every declared program gets a same-named executable shim in
`data_home()/bin`. Shims use only POSIX `sh`:

```sh
#!/bin/sh
exec "/absolute/path/to/data_home/plugins/name/bin/program" "$@"
```

This is a portability limitation: the generated shim assumes a POSIX `sh` is
available. `httk plugin path` returns the installed program path, and
`httk plugin run` executes it without requiring a PATH entry.

An existing shim blocks installation unless it is recorded as belonging to
the same plugin and program. Uninstall removes a shim only while it still
matches the plugin's target, so a foreign or changed shim is preserved.

## Trust and bundled workflows

Installing is explicit consent to acquire and place the supplied plugin.
Build commands execute with the user's account and environment policy, and
`httk plugin run` executes programs with the user's account. Installing a
plugin is not a sandbox.

When `httk-workflow` is installed, workflow packages listed in a plugin become
resolvable there by their package names. The workflow package manifest is
`httk_workflow.toml`; workflow-specific behavior is documented by
httk-workflow.
