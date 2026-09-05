import pytest
import hashlib

from httk.core.crypto import (
    ed25519_backend_available,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
)

_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
_PUBLIC = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
_SIGNATURE = bytes.fromhex(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def test_rfc_8032_vector_with_pure_backend() -> None:
    assert ed25519_public_key(_SEED, backend="pure") == _PUBLIC
    assert ed25519_sign(_SEED, b"", backend="pure") == _SIGNATURE
    assert ed25519_verify(_PUBLIC, b"", _SIGNATURE, backend="pure")


def test_invalid_keys_messages_and_signatures() -> None:
    with pytest.raises(ValueError):
        ed25519_public_key(b"short", backend="pure")
    assert not ed25519_verify(b"short", b"", _SIGNATURE, backend="pure")
    assert not ed25519_verify(_PUBLIC, b"changed", _SIGNATURE, backend="pure")
    assert not ed25519_verify(_PUBLIC, b"", _SIGNATURE[:-1], backend="pure")
    changed = bytearray(_SIGNATURE)
    changed[10] ^= 1
    assert not ed25519_verify(_PUBLIC, b"", bytes(changed), backend="pure")


def test_cryptography_parity_when_available() -> None:
    if not ed25519_backend_available("cryptography"):
        pytest.skip("cryptography is not installed")
    assert ed25519_public_key(_SEED, backend="cryptography") == _PUBLIC
    assert ed25519_sign(_SEED, b"", backend="cryptography") == _SIGNATURE
    assert ed25519_verify(_PUBLIC, b"", _SIGNATURE, backend="cryptography")


@pytest.mark.parametrize("backend", ["pure", "cryptography"])
@pytest.mark.parametrize("case", ["small-order", "noncanonical-y", "negative-zero", "scalar-order", "scalar-overflow"])
def test_malformed_points_and_scalars(backend, case):
    from httk.core.crypto import _L, _P

    if not ed25519_backend_available(backend):
        pytest.skip("optional backend unavailable")
    identity = (1).to_bytes(32, "little")
    if case == "small-order":
        key, signature = identity, identity + bytes(32)
    elif case == "noncanonical-y":
        key, signature = _P.to_bytes(32, "little"), _SIGNATURE
    elif case == "negative-zero":
        key, signature = ((1 << 255) | 1).to_bytes(32, "little"), _SIGNATURE
    elif case == "scalar-order":
        key, signature = _PUBLIC, _SIGNATURE[:32] + _L.to_bytes(32, "little")
    else:
        scalar = int.from_bytes(_SIGNATURE[32:], "little") + _L
        key, signature = _PUBLIC, _SIGNATURE[:32] + scalar.to_bytes(32, "little")
    assert not ed25519_verify(key, b"", signature, backend=backend)
    # Check the point encoding at both public-input positions.
    if case in {"small-order", "noncanonical-y", "negative-zero"}:
        assert not ed25519_verify(_PUBLIC, b"", key + _SIGNATURE[32:], backend=backend)


@pytest.mark.parametrize("index", range(8))
def test_generated_cross_backend_signatures(index):
    if not ed25519_backend_available("cryptography"):
        pytest.skip("optional backend unavailable")
    seed = hashlib.sha256(f"httk synthetic test seed {index}".encode()).digest()
    message = bytes(range(256)) * index
    public = ed25519_public_key(seed, backend="pure")
    assert public == ed25519_public_key(seed, backend="cryptography")
    signed = ed25519_sign(seed, message, backend="pure")
    assert signed == ed25519_sign(seed, message, backend="cryptography")
    for backend in ("pure", "cryptography"):
        assert ed25519_verify(public, message, signed, backend=backend)
        assert not ed25519_verify(public, message + b"changed", signed, backend=backend)


def test_backend_selection_without_optional_dependency(monkeypatch):
    from httk.core import crypto

    monkeypatch.setattr(crypto, "_cryptography_available", lambda: False)
    assert ed25519_sign(_SEED, b"") == _SIGNATURE
    assert ed25519_public_key(_SEED, backend="stdlib") == _PUBLIC
    assert ed25519_verify(_PUBLIC, b"", _SIGNATURE)
    with pytest.raises(ImportError, match="not installed"):
        ed25519_sign(_SEED, b"", backend="cryptography")
    with pytest.raises(ValueError, match="unknown"):
        ed25519_sign(_SEED, b"", backend="unknown")
