# The extensible command line

Installing *httk-core* provides the `httk` executable. Root options are
processed before command dispatch:

```console
httk -C DIR COMMAND [ARG ...]
httk -h
httk --version
httk help COMMAND
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

Command names use lowercase, hyphen-separated syntax. `help COMMAND` invokes
that command with `--help`. `help` by itself is equivalent to root help;
`help` and `version` are reserved names. See {doc}`registry` for the complete
discovery convention and registration surfaces.

## Plugins

The core-owned `httk plugin` command installs and manages plugins:

```console
httk plugin install SOURCE [--force]
httk plugin list
httk plugin show NAME [--json]
httk plugin path NAME PROGRAM
httk plugin run NAME PROGRAM [ARGS...]
httk plugin build NAME
httk plugin uninstall NAME
```

See {doc}`plugins` for source forms, manifests, builds, and program shims.

## Project initialization options

`httk project init` accepts the normal project options plus template options:

```console
httk project init [PATH] [--name NAME] [--description TEXT]
httk project init PATH --template SELECTOR
httk project init PATH --template SELECTOR --parameter NAME=VALUE
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
crystal structures *httk-io* registers the readers and writers and
*httk-atomistic* provides the structure model, so CIF and POSCAR convert both
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
