# Plugins

An *httk₂* plugin is a self-contained bundle of project templates, workflow
packages, and utility programs. Install one with `httk plugin install`:

```console
httk plugin install ./my-plugin
httk plugin install ./my-plugin.tar.gz
httk plugin install https://example.org/my-plugin.tar.gz
httk plugin install 'git+https://github.com/example/my-plugin.git@v1'
```

The source may be a directory, a `.tar`/`.tar.gz`/`.zip` archive, an HTTP(S)
archive URL, or a `git+https://…@ref` source. Use `--force` to replace an
installed plugin with the same name.

```console
httk plugin list
httk plugin show [--json] NAME...
httk plugin run NAME PROGRAM [ARGS...]
httk plugin path --program PROGRAM NAME...
httk plugin build NAME...
httk plugin uninstall NAME...
```

Programs are exposed through shims in `data_home()/bin`. Add that directory to
`PATH` when `httk plugin install` prints its PATH hint. Project templates are
selected with `httk project init --template`; see
{doc}`projects`.

The complete manifest, installation, build, shim, and trust details are in
{doc}`/details/plugins`.
