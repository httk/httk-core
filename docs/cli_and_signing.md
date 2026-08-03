# Extensible command line and signing

Installing *httk-core* provides the `httk` executable. Capability modules add
top-level commands from their `httk.registry.*` registration package, so a core
installation remains useful without importing optional command
implementations.

```console
httk --help
httk --version
httk -C project workflow store status .
httk help workflow
```

A module registers a command with metadata and a lazy implementation reference:

```python
from httk.core import register_cli_command

register_cli_command(
    "example",
    "example_package.cli:command",
    "run the example capability",
)
```

The handler contract is
`(argv: Sequence[str], context: CLIContext) -> int`. `context.program` is the
effective root program name and `context.cwd` is the working directory after
root `-C` processing. Command names are lowercase and hyphenated; duplicate
and reserved registrations are errors. Root help reads only the registration
metadata and does not resolve the lazy handler.

## Ed25519

The public signing functions use standard 32-byte Ed25519 private seeds:

```python
from httk.core.crypto import (
    ed25519_generate_seed,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
)

seed = ed25519_generate_seed()
public_key = ed25519_public_key(seed)
signature = ed25519_sign(seed, b"manifest digest")
assert ed25519_verify(public_key, b"manifest digest", signature)
```

The implementation uses `cryptography` when it is installed and otherwise
uses the tested stdlib RFC 8032 implementation. Pass `backend="pure"` to force
the portable backend, or query
`ed25519_backend_available("cryptography")`. Installing
`httk-core[default]` selects the accelerated dependency.
