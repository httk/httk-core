# The extensible command line

Installing *httk-core* provides the `httk` executable. Root options are
processed before command dispatch:

```console
httk -C DIR COMMAND [ARG ...]
httk -h
httk --version
httk help COMMAND [SUBCOMMAND ...]
```

`-C DIR` changes directory before dispatch, with git-style semantics. The
core-owned `httk project` command provides the project workflow; see
{doc}`projects`. There is no project-subcommand extension mechanism.

Capability modules register additional top-level commands under the
`httk.registry.cli.<module>` discovery tier. Registration is lazy, so root help
can list command summaries without importing command implementations.

```python
from httk.core import register_cli_command

register_cli_command(
    "example",
    "example_package.cli:command",
    "run the example capability",
)
```

The handler contract is
`(argv: Sequence[str], context: CLIContext) -> int`, where
{class}`httk.core.cli.CLIContext` supplies `program` and the post-`-C` `cwd`:

```python
from collections.abc import Sequence

from httk.core import CLIContext


def command(argv: Sequence[str], context: CLIContext) -> int:
    print(context.cwd)
    return 0
```

Command names use lowercase, hyphen-separated syntax. `help` works at every
level: `httk help COMMAND ...` and a trailing `help` after any subcommand chain
(e.g. `httk workflow runner help`) print that level's help; group levels
describe the group and list subcommands, leaf levels print usage with argument
definitions. `help` is only recognized before the first option, so it remains
usable as an option value. `help` by itself is equivalent to root help; `help`
and `version` are reserved names. See {doc}`registry` for the complete
discovery convention and registration surfaces.

## Plugins

The core-owned `httk plugin` command installs and manages plugins:

```console
httk plugin install [--force] SOURCE...
httk plugin list
httk plugin show [--json] NAME...
httk plugin path --program PROGRAM NAME...
httk plugin run NAME PROGRAM [ARGS...]
httk plugin build NAME...
httk plugin uninstall NAME...
```

See {doc}`plugins` for source forms, manifests, builds, and program shims.

## httk system

The core-owned `httk system reset` command removes both per-user httk state
directories: the configuration directory (`~/.config/httk`) and the data
directory (`~/.local/share/httk`). `HTTK_CONFIG_HOME` and `HTTK_DATA_HOME`
environment overrides are honored:

```console
httk system reset
httk system reset --force
```

Reset asks for confirmation when standard input is a terminal. Use `--force`
for non-interactive use. It exits with `0` after resetting, `1` when the
operation is declined, and `2` for invalid usage or an operational error.

## Project initialization options

`httk project init` accepts the normal project options plus template options:

```console
httk project init [--description TEXT] PATH...
httk project init --name NAME --template SELECTOR PATH
httk project init --template SELECTOR --parameter NAME=VALUE PATH...
httk project init --list-templates
```

`--parameter` is repeatable. `--list-templates` lists installed templates;
`--template` may also name an explicit template directory. See
{doc}`projects` for the selection and manifest rules.

## File conversion

The core-owned `httk convert` command loads a file with `httk.core.load` and
writes the result with `httk.core.save`, so anything loadable becomes anything
saveable:

```console
httk convert INPUT OUTPUT [--format FORMAT]
```

`INPUT` and `OUTPUT` are resolved against the working directory (the post-`-C`
`cwd`). `--format` selects the writer for an ambiguous `OUTPUT` and is forwarded
to `save`. The available formats come from the installed capability modules; for
crystal structures *httk-atomistic* registers the readers and writers and
provides the structure model, so CIF and POSCAR convert both
ways:

```console
httk convert structure.cif POSCAR
httk convert POSCAR structure.cif
```

`httk.core.load` and `httk.core.save` report an unrecognized input or output by
listing the extensions and filenames currently registered, so an unknown format
fails with a clear message and a nonzero exit code.

## Memory-guarded runs

The Linux-only `httk.core.memguard` module runs a command in its own process
group and kills the group when its summed RSS exceeds the selected budget:

```console
httk memguard --max-rss-gb 8 -- python -m pytest
```

It reports the peak RSS on standard error. The module requires a visible
`/proc` filesystem and is used for the repository Makefile test and benchmark
targets.
