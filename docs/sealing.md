# Sealing and manifests

*For campaign owners who need a finished project to stay provably unchanged.*

A project carries two signed integrity artifacts, both built from the same
deterministic record of what the tree contained at one moment, and both signed
over a domain-separated Ed25519 digest so one can never be replayed as the other:

- A **manifest** is a signed snapshot of every file in the tree. It answers *does
  this tree still match what was signed?* It lives at
  `httk_project/manifest.jsonl.bz2`.
- A **seal** is a signed statement that additionally records, for every project
  {ref}`member <project-members>`, the digest of that member's own seal — so a
  project seal transitively pins whole member subtrees without re-hashing them. It
  lives at `httk_project/seal.json`.

Neither is encryption or access control: both are public and detached. What they
buy is detection. Any later change to a covered byte becomes a discrepancy the
moment the artifact is verified.

## The record list

Both artifacts are built from one canonical record list: one entry per file,
symlink, and directory, sorted by path, never following symlinks. A file record
carries its size, SHA-256, and owner-execute bit, so a runner cannot be quietly
made (un)runnable. `httk.core.records.file_records` produces it; two seams keep
out what must not be covered — `fnmatch` exclusion patterns on posix relpaths,
and a `skip` predicate on absolute paths.

What a manifest excludes: the anchor material it cannot authenticate (the trust
anchors in `project.json`, private keys, remote credentials, and the manifest
file itself), plus whatever each member's handler names in its
`manifest_exclusions` — its own control and scratch directories, while its
payload stays covered. A seal excludes all of that *and* each member subtree as a
whole, because a member subtree is covered through its seal digest instead.

## Verdicts

Verifying either artifact answers two independent questions — *does it still
describe this tree* and *was it made by a key this project trusts* — and reports
both as one of three verdicts:

| Verdict | Meaning | Exit |
| --- | --- | --- |
| `valid_trusted` | the signature verifies and a signer is a pinned trust anchor | 0 |
| `valid_unknown_key` | the signature verifies, but nothing pins the signer | 3 |
| `invalid` | the artifact no longer describes the tree, or a signature does not verify | 1 |

The trust anchor is the key pinned in `project.json` — never the key an artifact
carries in its own header. The project's own signing seed lives inside the tree,
so anybody who can write the tree can re-sign it; a pin is what makes a signature
mean *who* signed, not merely *that it is self-consistent*.

## The manifest

```console
httk project manifest create            # write httk_project/manifest.jsonl.bz2
httk project manifest verify            # verify it against the tree
httk project manifest verify --trusted-key keys/collaborator.pub
```

`verify` prints `valid`/`invalid`, then a `<verdict>: <reason>` line, and exits
with the verdict's code. The programmatic equivalents are `create_manifest` and
`verify_manifest` in `httk.core.project`.

## Key refs

A seal is signed by one or more keys, each named by a *ref*:

| Ref | Signs with |
| --- | --- |
| `project` | the project's own signing seed, discovered from the tree |
| `identity` | the default operator identity |
| `identity:<name>` | a named operator identity |
| a path | a base64 Ed25519 seed file |

The default is the project's `seal_keys` member, or `project,identity` when it is
unset. `seal --keys REFS` overrides it for one call. A ref that cannot be
resolved is skipped with a warning rather than failing the seal; only resolving
*no* key at all is an error.

## Sealing, unsealing, and verifying

```console
httk project seal                       # seal loose files + every member's digest
httk project seal --keys project,identity
httk project verify-seal                # verify the project and every member seal
httk project verify-seal --shallow      # verify only the project seal
httk project unseal                     # remove the seal (prompts; --force to skip)
```

Every registered member must already be sealed, and every member kind must have a
registered handler; `seal` refuses otherwise, naming what is wrong. Registering
or moving a member is refused while the project is sealed — a seal a project
commits to must not change beneath it — so unseal first.

`verify-seal` prints one line per entry — `<level> <subject> <verdict> <reason>`
— with indented `<kind> <path>` discrepancy lines beneath any failing entry, then
a final `ok` / `UNTRUSTED` / `FAILED` word whose exit code matches the table
above. By default the project's pinned keys and the local identity's public key
are trusted, so a tree sealed by its own project or identity verifies as
`valid_trusted` without naming a key; `--trusted-key` adds more, as an `ed25519:`
key, a `sha256:` fingerprint, or a `*.pub` file. `--json` prints
`{ "entries": [...], "ok": ..., "trusted": ... }`.

## Not to be confused with

**`httk project export`.** The command that packages a project for distribution
as a signed ZIP is an *export*; *seal* here means only the integrity seal
described in this document.
