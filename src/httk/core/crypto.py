"""Ed25519 signing with an optional accelerated backend.

These signing primitives are used by project identity and trust.

All private keys accepted and returned by this module are standard 32-byte
Ed25519 seeds. The stdlib implementation follows RFC 8032 and is kept as a
portable fallback; ``cryptography`` is used automatically when installed.
The fallback uses variable-time Python arithmetic: use ``cryptography`` for
private-key operations where timing exposure matters. Both backends reject
non-canonical encodings and small-order public keys/signature points.
"""

import hashlib
import importlib
import importlib.util
import secrets
from typing import Any

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1, 1, 0)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P:
        x = (x * _I) % _P
    if x & 1:
        x = _P - x
    return x


_BY = (4 * pow(5, _P - 2, _P)) % _P
_BX = _xrecover(_BY)
_BASE = (_BX, _BY, 1, (_BX * _BY) % _P)


def _point_add(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = left
    x2, y2, z2, t2 = right
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * _D * t1 * t2) % _P
    d = (2 * z1 * z2) % _P
    e = b - a
    f = d - c
    g = d + c
    h = b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalar_multiply(point: tuple[int, int, int, int], scalar: int) -> tuple[int, int, int, int]:
    result = _IDENTITY
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = point
    inverse = pow(z, _P - 2, _P)
    affine_x = x * inverse % _P
    affine_y = y * inverse % _P
    return int.to_bytes(affine_y | ((affine_x & 1) << 255), 32, "little")


def _decode_point(encoded: bytes) -> tuple[int, int, int, int]:
    if len(encoded) != 32:
        raise ValueError("Ed25519 encoded point must be 32 bytes")
    integer = int.from_bytes(encoded, "little")
    y = integer & ((1 << 255) - 1)
    sign = integer >> 255
    if y >= _P:
        raise ValueError("non-canonical Ed25519 point")
    x = _xrecover(y)
    if (x & 1) != sign:
        x = _P - x
    if x == 0 and sign:
        raise ValueError("non-canonical Ed25519 point")
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P:
        raise ValueError("point is not on the Ed25519 curve")
    point = (x, y, 1, x * y % _P)
    if _encode_point(point) != encoded:
        raise ValueError("non-canonical Ed25519 point")
    return point


def _secret_scalar(seed: bytes) -> tuple[int, bytes]:
    digest = hashlib.sha512(seed).digest()
    scalar_bytes = bytearray(digest[:32])
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    return int.from_bytes(scalar_bytes, "little"), digest[32:]


def _hint(value: bytes) -> int:
    return int.from_bytes(hashlib.sha512(value).digest(), "little")


def _pure_public_key(seed: bytes) -> bytes:
    scalar, _ = _secret_scalar(seed)
    return _encode_point(_scalar_multiply(_BASE, scalar))


def _pure_sign(seed: bytes, message: bytes) -> bytes:
    scalar, prefix = _secret_scalar(seed)
    public_key = _encode_point(_scalar_multiply(_BASE, scalar))
    nonce = _hint(prefix + message) % _L
    encoded_r = _encode_point(_scalar_multiply(_BASE, nonce))
    challenge = _hint(encoded_r + public_key + message) % _L
    return encoded_r + int.to_bytes((nonce + challenge * scalar) % _L, 32, "little")


def _verification_points(
    public_key: bytes, signature: bytes
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Apply the same public-input validation policy before either verifier."""
    if len(public_key) != 32 or len(signature) != 64:
        return None
    scalar = int.from_bytes(signature[32:], "little")
    if scalar >= _L:
        return None
    try:
        public_point = _decode_point(public_key)
        r_point = _decode_point(signature[:32])
    except ValueError:
        return None
    # A backend installation must not change whether a small-order identity key
    # (which can admit signatures without a secret) passes project verification.
    if _encode_point(_scalar_multiply(public_point, 8)) == _encode_point(_IDENTITY):
        return None
    if _encode_point(_scalar_multiply(r_point, 8)) == _encode_point(_IDENTITY):
        return None
    return public_point, r_point


def _pure_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    points = _verification_points(public_key, signature)
    if points is None:
        return False
    public_point, r_point = points
    scalar = int.from_bytes(signature[32:], "little")
    challenge = _hint(signature[:32] + public_key + message) % _L
    left = _scalar_multiply(_BASE, scalar)
    right = _point_add(r_point, _scalar_multiply(public_point, challenge))
    return _encode_point(left) == _encode_point(right)


def _cryptography_available() -> bool:
    return importlib.util.find_spec("cryptography") is not None


def _cryptography_modules() -> tuple[Any, Any, Any]:
    serialization = importlib.import_module("cryptography.hazmat.primitives.serialization")
    ed25519 = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
    exceptions = importlib.import_module("cryptography.exceptions")
    return serialization, ed25519, exceptions


def ed25519_backend_available(backend: str = "cryptography") -> bool:
    """Return whether *backend* can perform Ed25519 operations.

    :param backend: Backend name: ``"cryptography"``, ``"pure"``, or ``"stdlib"``.
    :return: Whether the selected backend is available.
    :raises ValueError: If ``backend`` is not a supported backend name.
    """

    if backend in {"pure", "stdlib"}:
        return True
    if backend == "cryptography":
        return _cryptography_available()
    raise ValueError(f"unknown Ed25519 backend: {backend!r}")


def _backend(backend: str | None) -> str:
    if backend is None or backend == "auto":
        return "cryptography" if _cryptography_available() else "pure"
    if backend not in {"cryptography", "pure", "stdlib"}:
        raise ValueError(f"unknown Ed25519 backend: {backend!r}")
    if backend == "cryptography" and not _cryptography_available():
        raise ImportError("the cryptography Ed25519 backend is not installed")
    return "pure" if backend == "stdlib" else backend


def _seed(value: bytes) -> bytes:
    result = bytes(value)
    if len(result) != 32:
        raise ValueError("Ed25519 private seed must be exactly 32 bytes")
    return result


def ed25519_generate_seed() -> bytes:
    """Generate a standard 32-byte Ed25519 private seed.

    :return: A newly generated private seed.
    """

    return secrets.token_bytes(32)


def ed25519_public_key(seed: bytes, *, backend: str | None = None) -> bytes:
    """Derive the public key for a private seed.

    :param seed: 32-byte Ed25519 private seed.
    :param backend: Backend name, ``"auto"``, or ``None`` to select the accelerated backend when available.
    :return: The 32-byte Ed25519 public key.
    :raises ValueError: If ``seed`` is not exactly 32 bytes or ``backend`` is unsupported.
    :raises ImportError: If the requested ``cryptography`` backend is unavailable.
    """

    private_seed = _seed(seed)
    if _backend(backend) == "cryptography":
        serialization, ed25519, _ = _cryptography_modules()
        return (
            ed25519.Ed25519PrivateKey.from_private_bytes(private_seed)
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
    return _pure_public_key(private_seed)


def ed25519_sign(seed: bytes, message: bytes, *, backend: str | None = None) -> bytes:
    """Return an RFC 8032 Ed25519 signature for ``message``.

    :param seed: 32-byte Ed25519 private seed.
    :param message: Bytes to sign.
    :param backend: Backend name, ``"auto"``, or ``None`` to select the accelerated backend when available.
    :return: The 64-byte Ed25519 signature.
    :raises ValueError: If ``seed`` is not exactly 32 bytes or ``backend`` is unsupported.
    :raises ImportError: If the requested ``cryptography`` backend is unavailable.
    """

    private_seed = _seed(seed)
    payload = bytes(message)
    if _backend(backend) == "cryptography":
        _, ed25519, _ = _cryptography_modules()
        return ed25519.Ed25519PrivateKey.from_private_bytes(private_seed).sign(payload)
    return _pure_sign(private_seed, payload)


def ed25519_verify(
    public_key: bytes,
    message: bytes,
    signature: bytes,
    *,
    backend: str | None = None,
) -> bool:
    """Return whether ``signature`` is valid, treating malformed input as false.

    Both backends require canonical points, a scalar below the group order,
    and non-small-order public and signature points. These input checks use
    public data only; private-key arithmetic remains in the selected backend.

    :param public_key: 32-byte Ed25519 public key.
    :param message: Bytes whose signature is being checked.
    :param signature: 64-byte Ed25519 signature.
    :param backend: Backend name, ``"auto"``, or ``None`` to select the accelerated backend when available.
    :return: Whether the signature verifies for the public key and message.
    :raises ValueError: If ``backend`` is unsupported.
    :raises ImportError: If the requested ``cryptography`` backend is unavailable.
    """

    key = bytes(public_key)
    payload = bytes(message)
    signed = bytes(signature)
    if len(key) != 32 or len(signed) != 64:
        return False
    if _backend(backend) == "cryptography":
        if _verification_points(key, signed) is None:
            return False
        _, ed25519, exceptions = _cryptography_modules()
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(key).verify(signed, payload)
        except (exceptions.InvalidSignature, ValueError):
            return False
        return True
    return _pure_verify(key, payload, signed)
