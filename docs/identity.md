# Operator identity

An *operator identity* is the attribution recorded on a document a user
publishes: a name, an email, and an Ed25519 signing key. It says *who*
published something and never *what they may do* — a signature is attribution,
never authorization.

Identity is per-user state. The signing keys live under
`config_home()/"keys"` and the named-identity configuration lives in
`config_home()/"identity.json"`, both honouring `HTTK_CONFIG_HOME` through
{func}`httk.core.userdirs.config_home`. Redirecting that one environment
variable relocates the entire per-user identity store, which is how tests and
isolated runs keep out of a real user's configuration.

## Command line

The identity store is set up and managed from the root command line. `httk init`
records the bare name and email and ensures the default signing key; `httk
identity` manages the named identities.

```console
httk init --name "Alice" --email alice@example.test
httk identity add alice --name "Alice" --email alice@example.test
httk identity add ci_bot --name "CI" --email ci@example.test --default
httk identity list --json
httk identity default alice
httk identity remove ci_bot
```

`httk init` prompts for a missing name or email on a terminal and, with
`--non-interactive`, refuses one instead. It is idempotent: an existing key is
kept while the recorded name and email are updated. See {doc}`cli` for the full
command reference.

## Named identities

```python
from httk.core.identity import add_identity, resolve_operator_identity

add_identity("alice", "Alice", "alice@example.test")   # the first becomes default
add_identity("ci_bot", "CI", "ci@example.test", make_default=True)

resolve_operator_identity(None).short         # "ci_bot" — the default
resolve_operator_identity("alice").label      # "Alice <alice@example.test>"
```

`add_identity`, `set_default_identity`, and `remove_identity` maintain
`identity.json`; `initialize_identity(name, email)` records a bare (un-named)
identity and its default key. `resolve_operator_identity` also accepts a literal
`Name <email>` selector for one-off attribution.

## Signing documents

Signing is optional by construction: a caller with no identity key returns the
document unchanged, and a verifier accepts an unsigned document. That is what
keeps a mixed deployment — some installations with keys, some without — working.

```python
from httk.core.identity import sign_document, verify_document

signed = sign_document({"format": "outcome", "value": 1})
result = verify_document(signed)
assert result.present and result.valid
```

`sign_document` adds an `operator_key` and a detached `signature` covering the
canonical JSON of every other member, domain-separated so a signature made for
one purpose cannot be replayed against another. `verify_document` reports
whether a signature was `present` and whether it was `valid`; an absent
signature is reported as absent rather than as a failure.
