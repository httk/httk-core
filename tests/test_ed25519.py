import pytest

from httk.core import (
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
