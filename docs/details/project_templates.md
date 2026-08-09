# Project templates in detail

Project templates are directories containing `httk_project_template.toml`.
They can be selected by an explicit directory, by `plugin:id`, or by a bare
template ID when exactly one installed template has that ID. A bare ID shared
by multiple plugins is ambiguous and must be qualified.

## The `httk_project_template.toml` manifest

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

### `[template]`

`id` is required and must match `[a-z0-9._-]+`; it must not be `.` or `..`,
and must not start with `-`. `description` is an optional string.

`files` is an optional array of relative POSIX members. Each member may be a
regular file or a directory. Members must remain below the template root,
must not be absolute, contain empty components, `.`, or `..`, or traverse a
symlink. They must be unique and may not overlap by containment. The manifest
itself, `httk_project_template.toml`, and the instantiate hook may not be
listed. Directory members are copied recursively; symlinks and special files
inside them are rejected during instantiation.

### `[template.instantiate]`

The table is optional and accepts the required `file` key. A `.py` file is run
with the current Python interpreter. A non-Python file must be an executable
regular member. The hook is required when the template declares any
parameters.

### `[template.parameters.<name>]`

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
httk project init demo --template starter \
  --parameter name='"Ada"' --parameter count=3 --parameter enabled=true
```

The quotes around `"Ada"` are needed because an unquoted `Ada` is the JSON
fallback string, while a value such as `3` is parsed as an integer. Unknown
parameters, missing mandatory parameters, and values of the wrong type fail
before the project directory is created.

## The instantiate hook

The hook receives one JSON request on standard input. It runs with the project
directory as its current working directory (`cwd`) and with the selected
template files already copied. The request envelope is:

```json
{
  "format": "httk-project-template-instantiate",
  "format_version": 1,
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

## Instantiation and rollback

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
