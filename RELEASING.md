# Releasing `httk-core`

Releases are built and published by GitHub Actions. PyPI authentication uses
Trusted Publishing, so the repository does not need a stored PyPI API token.

## One-time setup

1. Create accounts on [PyPI](https://pypi.org) and
   [TestPyPI](https://test.pypi.org), and enable two-factor authentication.
2. In the GitHub repository settings, create environments named `pypi` and
   `testpypi`. Configure a required reviewer for `pypi` (and optionally for
   `testpypi`); restricting the `pypi` environment to tags matching `v*` is
   also recommended.
3. On PyPI, add a pending GitHub Trusted Publisher with these values:

   - PyPI project name: `httk-core`
   - Owner: `httk`
   - Repository: `httk-core`
   - Workflow: `release.yml`
   - Environment: `pypi`

4. Add the corresponding pending publisher on TestPyPI, using the environment
   `testpypi` instead.

A pending publisher creates the project during its first upload. It does not
reserve the project name before then.

## Prepare and check a release

Update `project.version` in `pyproject.toml`. After making dependency changes,
regenerate and commit the documentation lock before tagging:

```console
make docs-lock
```

From a Python 3.12 environment, install the development tools and run the
complete local check:

```console
python -m pip install -e ".[dev,docs,release]"
make release-check
```

`make release-check` includes the cheap offline documentation lock-freshness
check, in addition to formatting, static analysis, tests, strict documentation,
an isolated sdist/wheel build, and strict package-metadata checks. Before
tagging, run `make docs-lock-check` for the required full clean-environment
locked installation and strict docs build; this is a network check. The
resulting package files are written to `dist/`.

Versions on package indexes are immutable. Use a new development or release
candidate version when repeating an upload, for example `2.0.0rc1` followed by
`2.0.0`.

## TestPyPI

Run the **Publish package** workflow manually in GitHub Actions. A manual run
publishes to TestPyPI only. To retry a TestPyPI upload without committing a version bump, pass the
optional `version_suffix` workflow input (e.g. `.post1` or `rc2`); it is
appended to `project.version` for that build only.
When the workflow run has completed (approving the
`testpypi` environment first, if it has a required reviewer), test the artifact
in a fresh environment:

```console
python -m venv /tmp/httk-core-test
/tmp/httk-core-test/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ --no-deps httk-core==2.0.0
/tmp/httk-core-test/bin/python -c "import httk.core"
```

Replace `2.0.0` with the version being tested. `--no-deps` is appropriate here
because `httk-core` deliberately has no runtime dependencies.

## PyPI

1. Confirm that `make release-check` succeeds on the exact commit to release.
2. Push the commit and create a GitHub release whose tag is `v` followed by the
   package version, for example `v2.0.0`. The tag push triggers
   `docs-release.yml`, which validates tag/package-version/lock consistency and
   publishes the immutable `vX.Y.Z/` documentation tree.
3. Publish the GitHub release and approve the protected `pypi` environment.
4. Verify the release from a fresh environment with `pip install httk-core`.

The workflow rejects a Git tag that does not match `project.version`, rebuilds
the distributions from the tagged source, checks them, and publishes them via
PyPI Trusted Publishing.

## Repairing a generated release site

`docs-repair.yml` is reserved for replacing a known-bad generated artifact
after the tagged source and locked build have been verified. It is manually
triggered for one `vX.Y.Z` tag and requires approval from the protected
`docs-repair` GitHub environment; it does not change package source or release
immutability policy.

## Half-published states

Documentation publishes on the tag push independently of PyPI publication. If
PyPI publication is abandoned after tagging, handle the published documentation
version through the environment-approved repair path. This ordering is an
intentional choice in the versioned-documentation plan.
