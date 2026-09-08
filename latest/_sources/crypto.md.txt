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

## Security boundaries and assessment

The pure-Python backend uses variable-time integer arithmetic and branches on
secret scalar bits. It is a portability fallback, not a constant-time private-key
implementation. Use the accelerated backend for signing and public-key derivation
when local timing exposure matters. Backend selection does not change seed format
or valid signatures.

Verification uses the same input policy with either backend: canonical point
encodings, a scalar below the group order, and rejection of small-order public
keys and signature points. This deliberately retains the portable backend's
stricter small-order policy. The previous accelerated path accepted an identity
point key with an identity-point/zero-scalar signature for arbitrary messages;
installing an optional dependency must not widen the project's identity policy.
The shared checks examine public inputs only; accelerated private-key operations
still remain inside `cryptography`.

The assessment covers `httk.core.crypto`, its project manifest/seal/export
consumers, and the signature boundary used by identity ledgers. Tests include the
RFC known-answer vector, deterministic synthetic cross-backend signatures,
modified messages, truncated signatures, noncanonical encodings, small-order
points, scalar boundaries, and optional-backend selection. It does not constitute
an independent cryptographic audit, exhaustive malformed-input corpus, or timing
certification. Signature validity alone never establishes that a key is trusted;
callers must retain their signer authorization and trust checks.

The algorithm and decoding reference is
[RFC 8032](https://www.rfc-editor.org/rfc/rfc8032), especially sections 5.1.3,
5.1.7, 7.1, and 8. Backend integration follows the
[cryptography Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
