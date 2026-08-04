# Cryptography

Ed25519 lives in *httk-core* so that any *httk* module can sign manifests and
output data without adding a cryptography dependency of its own. Signed
project manifests in *httk-workflow* are the canonical consumer.

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

`ed25519_public_key` derives a 32-byte public key from a seed.
`ed25519_sign` returns a 64-byte RFC 8032 signature, and `ed25519_verify`
returns whether it is valid. The default backend uses `cryptography` when it
is installed and otherwise uses the stdlib RFC 8032 implementation.

Pass `backend="pure"` to force the portable implementation, or use
`ed25519_backend_available("cryptography")` to test the optional backend.
Installing `httk-core[default]` selects the `cryptography` dependency.
