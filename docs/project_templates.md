# Project templates

An *httk₂* project template supplies files and, optionally, a hook that
generates more project content. Templates can be bundled by plugins or used
directly from a directory containing `httk_project_template.toml`.

Install a plugin, then initialize a project from one of its templates:

```console
httk plugin install ./my-plugin
httk project init my-project --template my-plugin:starter --parameter n=3
```

List installed templates and their plugin-qualified selectors with:

```console
httk project init --list-templates
```

An explicit template directory works without a plugin:

```console
httk project init my-project --template ./templates/starter
```

See {doc}`/details/project_templates` for the manifest schema, hook protocol,
parameters, copying order, and rollback behavior.
