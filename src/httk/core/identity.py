"""Per-user operator identity: signing keys, named identities, and signatures.

An *operator identity* is the attribution recorded on a document a user
publishes — a name, an email, and an Ed25519 signing key. It says *who*
published something and never *what they may do*: a signature is attribution,
never authorization.

Identity keys live under ``config_home()/"keys"`` and the named-identity
configuration lives in ``config_home()/"identity.json"``. Both honour
``HTTK_CONFIG_HOME`` through :func:`httk.core.userdirs.config_home`, so a test
or an isolated run redirects the whole per-user identity store with one
environment variable.

Signing is optional by construction: a caller with no identity key returns the
document unchanged, and a verifier accepts an unsigned document. That is what
keeps a mixed deployment — some installations with keys, some without — working.
"""

import base64
import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from httk.core.crypto import (
    ed25519_generate_seed,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
)
from httk.core.userdirs import config_home

from ._json import json_bytes, read_json, write_json_atomic

__all__ = [
    "IDENTITY_CONFIG_FORMAT",
    "IDENTITY_CONFIG_FORMAT_VERSION",
    "IDENTITY_KEY_MEMBER",
    "IDENTITY_SIGNATURE_DOMAIN",
    "IDENTITY_SIGNATURE_MEMBER",
    "DocumentSignature",
    "OperatorIdentity",
    "add_identity",
    "ensure_identity_key",
    "identity_config_path",
    "identity_key_paths",
    "identity_public_key",
    "identity_seed",
    "initialize_identity",
    "keys_home",
    "read_identity_config",
    "remove_identity",
    "resolve_operator_identity",
    "set_default_identity",
    "sign_document",
    "signature_digest",
    "verify_document",
    "write_identity_config",
]

#: The format tag and version of ``identity.json``.
IDENTITY_CONFIG_FORMAT = "httk-identity"
IDENTITY_CONFIG_FORMAT_VERSION = 1

#: Domain separation of every detached identity signature, so a digest signed
#: for one purpose can never be replayed as a signature of something else.
IDENTITY_SIGNATURE_DOMAIN = b"httk-identity-v2\0"
#: The members an identity signature adds to the document it signs.
IDENTITY_KEY_MEMBER = "operator_key"
IDENTITY_SIGNATURE_MEMBER = "signature"

_IDENTITY_SHORT = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_LITERAL_OPERATOR = re.compile(r"\A\s*(?:(?P<name>[^<>\s](?:[^<>]*[^<>\s])?)\s+)?<(?P<email>[^\s<>]*@[^\s<>]*)>\s*\Z")


def keys_home() -> Path:
    """Return where this user's identity keys live.

    :return: Per-user identity key directory.
    """

    return config_home() / "keys"


def identity_config_path() -> Path:
    """Return the path of this user's identity configuration file.

    :return: Per-user identity configuration path.
    """

    return config_home() / "identity.json"


def read_identity_config() -> dict[str, object]:
    """Read the identity configuration, returning an empty mapping if absent.

    A document of an unrecognized format or version is refused by name rather
    than read as if its members meant what this implementation means by them.

    :return: Identity configuration members, or an empty mapping when no file exists.
    :raises ValueError: If the file is not a supported identity configuration document.
    """

    path = identity_config_path()
    if not path.exists():
        return {}
    value = read_json(path)
    recorded_format = value.get("format")
    if recorded_format != IDENTITY_CONFIG_FORMAT:
        raise ValueError(
            f"identity configuration is not a {IDENTITY_CONFIG_FORMAT} document but {recorded_format!r}: {path}"
        )
    version = value.get("format_version")
    if version != IDENTITY_CONFIG_FORMAT_VERSION:
        raise ValueError(
            f"identity configuration {path} uses {IDENTITY_CONFIG_FORMAT} version {version!r}, "
            f"but this implementation reads version {IDENTITY_CONFIG_FORMAT_VERSION}"
        )
    return value


def write_identity_config(values: Mapping[str, object]) -> Path:
    """Write a versioned identity configuration atomically and durably.

    :param values: Identity configuration members to write.
    :return: Path of the written configuration file.
    """

    value = dict(values)
    value.setdefault("format", IDENTITY_CONFIG_FORMAT)
    value.setdefault("format_version", IDENTITY_CONFIG_FORMAT_VERSION)
    path = identity_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, value, durable=True)
    return path


def identity_key_paths(short: str | None = None) -> tuple[Path, Path]:
    """Return the paths of the local identity seed and public key.

    :param short: Named identity short name, or ``None`` for the default key.
    :return: Seed path followed by public-key path.
    :raises ValueError: If ``short`` is not a valid identity short name.
    """
    root = keys_home()
    if short is None:
        return root / "identity.seed", root / "identity.pub"
    _validate_identity_short(short)
    return root / f"identity-{short}.seed", root / f"identity-{short}.pub"


def _validate_identity_short(short: str) -> str:
    if not isinstance(short, str) or _IDENTITY_SHORT.fullmatch(short) is None:
        raise ValueError("identity short name must match [a-z0-9][a-z0-9_-]*")
    return short


def _ensure_identity_key_paths(private_path: Path, public_path: Path) -> tuple[Path, Path]:
    """Create one standard Ed25519 keypair with the hardened key semantics."""

    if private_path.is_symlink() or public_path.is_symlink():
        raise ValueError(f"refusing symlink identity key path: {private_path} or {public_path}")

    try:
        private_path.lstat()
    except FileNotFoundError:
        seed = ed25519_generate_seed()
        private_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = _write_key_file_atomic(
            private_path,
            base64.b64encode(seed).decode("ascii") + "\n",
            0o600,
            exclusive=True,
        )
        if not created:
            seed = _read_existing_seed(private_path)
            reused_seed = True
        else:
            reused_seed = False
    else:
        seed = _read_existing_seed(private_path)
        reused_seed = True

    public_text = base64.b64encode(ed25519_public_key(seed)).decode("ascii") + "\n"
    installed = _write_key_file_atomic(
        public_path,
        public_text,
        0o644,
        exclusive=not reused_seed,
    )
    if not installed and _read_key_file(public_path).strip() != public_text.strip():
        raise ValueError(f"identity public key already exists and does not match the seed: {public_path}")
    return private_path, public_path


def _decode_seed(encoded: bytes, path: Path) -> bytes:
    try:
        seed = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError(f"identity key is not a standard 32-byte Ed25519 seed: {path}") from exc
    if len(seed) != 32:
        raise ValueError(f"identity key is not a standard 32-byte Ed25519 seed: {path}")
    return seed


def _read_seed_no_follow(path: Path) -> bytes:
    """Read an identity seed via ``O_NOFOLLOW`` without touching its mode.

    A symlinked, unreadable, or malformed seed is refused with a
    :class:`ValueError`; a genuinely missing file raises
    :class:`FileNotFoundError` so a probe can treat an absent key as *unsigned*
    without also swallowing a refusal.

    :param path: The seed file to read.
    :return: The decoded 32-byte seed.
    :raises FileNotFoundError: If the seed file does not exist.
    :raises ValueError: If the seed is a symlink, unreadable, or not a standard seed.
    """

    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError(f"cannot safely read identity seed: {path}") from exc
    with os.fdopen(descriptor, "rb") as stream:
        encoded = stream.read().strip()
    return _decode_seed(encoded, path)


def _read_existing_seed(path: Path) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError(f"cannot safely read identity seed: {path}") from exc
    with os.fdopen(descriptor, "rb") as stream:
        encoded = stream.read().strip()
        seed = _decode_seed(encoded, path)
        os.fchmod(stream.fileno(), 0o600)
        return seed


def _read_key_file(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ValueError(f"cannot safely read identity key: {path}") from exc
    with os.fdopen(descriptor, encoding="ascii") as stream:
        return stream.read()


def _write_key_file_atomic(path: Path, text: str, mode: int, *, exclusive: bool = False) -> bool:
    """Write one key file atomically with an explicit mode.

    :param path: Destination key file.
    :param text: ASCII contents to write.
    :param mode: Permission bits for the written file.
    :param exclusive: Whether an existing file must be preserved rather than replaced.
    :return: Whether this call installed the file (``False`` when it already existed and ``exclusive`` is set).
    """

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError:
                return False
        else:
            os.replace(temporary, path)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def ensure_identity_key(short: str | None = None) -> tuple[Path, Path]:
    """Create the user's standard Ed25519 identity key if it is absent.

    :param short: Named identity short name, or ``None`` for the default key.
    :return: Seed path followed by public-key path.
    :raises ValueError: If an existing seed is not a standard Ed25519 seed.
    """

    paths = identity_key_paths() if short is None else identity_key_paths(short)
    return _ensure_identity_key_paths(*paths)


@dataclass(frozen=True)
class OperatorIdentity:
    """One configured operator attribution identity.

    :param short: Named identity short name, or ``None`` for the default identity.
    :param name: Operator name.
    :param email: Operator email address.
    :param seed_path: Path of the signing seed, or ``None`` when none exists yet.
    """

    short: str | None
    name: str
    email: str
    seed_path: Path | None

    @property
    def label(self) -> str:
        """Return the ``Name <email>`` attribution label.

        :return: The operator's attribution label.
        """

        return f"{self.name} <{self.email}>"


def _validate_operator_identity_fields(name: str, email: str) -> None:
    if any(character in name for character in "<>\r\n"):
        raise ValueError("identity name must not contain '<', '>', or newlines")
    if not email or "@" not in email or any(character.isspace() or character in "<>" for character in email):
        raise ValueError("identity email must be nonempty, contain '@', and contain no whitespace or angle brackets")


def _configured_identities(values: Mapping[str, object]) -> dict[str, tuple[str, str]]:
    raw = values.get("identities")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("identity configuration key 'identities' must be an object")
    result: dict[str, tuple[str, str]] = {}
    for short, item in raw.items():
        _validate_identity_short(short)
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("email"), str)
        ):
            raise ValueError(f"identity {short!r} must contain string name and email")
        _validate_operator_identity_fields(item["name"], item["email"])
        result[short] = (item["name"], item["email"])
    return result


def _default_operator_identity(values: Mapping[str, object]) -> OperatorIdentity:
    identities = _configured_identities(values)
    selected = values.get("default_identity")
    if "default_identity" in values:
        if not isinstance(selected, str) or selected not in identities:
            raise ValueError("the configured default identity does not name a configured identity")
        short = selected
    elif len(identities) == 1:
        short = next(iter(identities))
    else:
        name = values.get("name")
        email = values.get("email")
        if not isinstance(name, str) or not name or not isinstance(email, str) or not email:
            raise ValueError("no operator identity is configured")
        return OperatorIdentity(None, name, email, identity_key_paths()[0])
    name, email = identities[short]
    return OperatorIdentity(short, name, email, identity_key_paths(short)[0])


def _truly_unconfigured(values: Mapping[str, object]) -> bool:
    if "default_identity" in values:
        return False
    if "identities" in values:
        identities = values["identities"]
        if not isinstance(identities, Mapping) or identities:
            return False
    return all(key not in values or values[key] in (None, "") for key in ("name", "email"))


def resolve_operator_identity(selector: str | None) -> OperatorIdentity:
    """Resolve a configured identity or a literal ``Name <email>`` label.

    :param selector: A configured short name, a literal ``Name <email>`` label, or ``None`` for the default.
    :return: The resolved operator identity.
    :raises ValueError: If the selector is malformed, unknown, or the default is unresolvable.
    """

    values = read_identity_config()
    if selector is not None and "<" in selector:
        literal = _LITERAL_OPERATOR.fullmatch(selector)
        if literal is None:
            raise ValueError(
                'literal identity must match "NAME <EMAIL>" with a closing ">" and an email containing "@"'
            )
        name = (literal.group("name") or "").strip()
        email = literal.group("email")
        try:
            seed_path = _default_operator_identity(values).seed_path
        except ValueError:
            if not _truly_unconfigured(values):
                raise
            seed_path = None
        return OperatorIdentity(None, name.strip(), email, seed_path)
    identities = _configured_identities(values)
    if selector is not None:
        if selector not in identities:
            shorts = ", ".join(sorted(identities)) or "(none)"
            raise ValueError(f"unknown identity {selector!r}; configured identities: {shorts}")
        name, email = identities[selector]
        return OperatorIdentity(selector, name, email, identity_key_paths(selector)[0])
    return _default_operator_identity(values)


def initialize_identity(name: str, email: str) -> dict[str, object]:
    """Record a bare operator identity and ensure its default signing key.

    This is the un-named identity: the top-level ``name`` and ``email`` that the
    default resolves to when no named identity is configured, signed with the
    default key. Named identities are added with :func:`add_identity`.

    :param name: Operator name to record.
    :param email: Operator email address to record.
    :return: The resulting identity configuration members.
    """

    values = read_identity_config()
    values.update(
        {
            "format": IDENTITY_CONFIG_FORMAT,
            "format_version": IDENTITY_CONFIG_FORMAT_VERSION,
            "name": name,
            "email": email,
        }
    )
    write_identity_config(values)
    ensure_identity_key()
    return values


def add_identity(short: str, name: str, email: str, *, make_default: bool = False) -> dict[str, object]:
    """Create and configure one named operator identity and its signing key.

    The first identity added becomes the default; a later identity becomes the
    default only when ``make_default`` is set. When a default is already
    configured it is left in place unless overridden.

    :param short: Short identity name matching ``[a-z0-9][a-z0-9_-]*``.
    :param name: Operator name.
    :param email: Operator email address.
    :param make_default: Whether to make this identity the default.
    :return: The resulting identity configuration members.
    :raises ValueError: If the short name is taken or the name/email are unforwardable.
    """

    values = read_identity_config()
    identities = _configured_identities(values)
    if short in identities:
        raise ValueError(f"identity already exists: {short}")
    identity_key_paths(short)
    _validate_operator_identity_fields(name, email)
    had_default = "default_identity" in values
    previous_default = values.get("default_identity")
    ensure_identity_key(short)
    identities[short] = (name, email)
    values["identities"] = {name_: {"name": item[0], "email": item[1]} for name_, item in identities.items()}
    selected_default = short if len(identities) == 1 or make_default else previous_default
    if len(identities) == 1 or make_default or had_default:
        values["default_identity"] = selected_default
    write_identity_config(values)
    return values


def set_default_identity(short: str) -> dict[str, object]:
    """Select the default named operator identity.

    :param short: Short name of a configured identity.
    :return: The resulting identity configuration members.
    :raises ValueError: If ``short`` is not a configured identity.
    """

    values = read_identity_config()
    identities = _configured_identities(values)
    if short not in identities:
        shorts = ", ".join(sorted(identities)) or "(none)"
        raise ValueError(f"unknown identity {short!r}; configured identities: {shorts}")
    values["default_identity"] = short
    write_identity_config(values)
    return values


def remove_identity(short: str) -> dict[str, object]:
    """Remove one named identity, leaving its key files untouched.

    The key files are deliberately kept: removing an identity forgets its
    attribution, but a signature it already produced must stay verifiable.

    :param short: Short name of a configured identity.
    :return: The resulting identity configuration members.
    :raises ValueError: If ``short`` is not configured, or is the default while others remain.
    """

    values = read_identity_config()
    identities = _configured_identities(values)
    if short not in identities:
        shorts = ", ".join(sorted(identities)) or "(none)"
        raise ValueError(f"unknown identity {short!r}; configured identities: {shorts}")
    default = values.get("default_identity")
    if default == short and len(identities) > 2:
        raise ValueError(f"cannot remove default identity {short!r}; choose another default first")
    identities.pop(short)
    values["identities"] = {name_: {"name": item[0], "email": item[1]} for name_, item in identities.items()}
    if default == short:
        if len(identities) == 1:
            values["default_identity"] = next(iter(identities))
        else:
            values.pop("default_identity", None)
    if not identities:
        values.pop("default_identity", None)
    write_identity_config(values)
    return values


def identity_seed(seed_path: Path | None = None) -> bytes | None:
    """Return the local identity seed, or ``None`` when no key was created.

    Nothing here creates a key. An installation that never configured an
    identity simply has none, and every caller treats that as *unsigned* rather
    than as an error, which is what keeps a mixed deployment working.

    :param seed_path: Explicit seed path, or ``None`` to resolve the default.
    :return: The local seed, or no value when no valid key exists.
    :raises ValueError: If the default is unresolvable or a present seed is unreadable.
    """

    if seed_path is None:
        values = read_identity_config()
        try:
            seed_path = _default_operator_identity(values).seed_path
        except ValueError:
            # A bare installation with only a default key and no configured
            # identity still signs with that key; an installation that has
            # configured identities but no resolvable default is ambiguous and
            # must refuse rather than silently pick one.
            if not _truly_unconfigured(values):
                raise
            seed_path = identity_key_paths()[0]
    if seed_path is None:
        return None
    try:
        return _read_seed_no_follow(seed_path)
    except FileNotFoundError:
        return None


def identity_public_key(seed_path: Path | None = None) -> str | None:
    """Return the recorded local identity public key, or ``None``.

    :param seed_path: Explicit seed path, or ``None`` to resolve the default.
    :return: Encoded public key, or ``None`` when no identity exists.
    """

    seed = identity_seed(seed_path)
    return None if seed is None else "ed25519:" + base64.b64encode(ed25519_public_key(seed)).decode("ascii")


def signature_digest(document: Mapping[str, object]) -> bytes:
    """Return the domain-separated digest one identity signature covers.

    The digest covers the whole document except the signature itself, in the
    same canonical JSON every other httk document is hashed as, so the signing
    key and the signed members travel together and neither can be swapped.

    :param document: Document whose detached signature is being calculated.
    :return: Domain-separated digest of the unsigned document.
    """

    body = {name: value for name, value in document.items() if name != IDENTITY_SIGNATURE_MEMBER}
    return hashlib.sha256(IDENTITY_SIGNATURE_DOMAIN + json_bytes(body)).digest()


def sign_document(document: Mapping[str, object], *, seed_path: Path | None = None) -> dict[str, object]:
    """Return *document* with a detached identity signature, when one is possible.

    Signing is optional by construction: a caller with no identity key returns
    the document unchanged, and a verifier accepts an unsigned document. The
    signature is attribution — it says which identity published this — and never
    authorization: nothing is permitted because a document is signed.

    :param document: Document to copy and optionally sign.
    :param seed_path: Explicit seed path, or ``None`` to resolve the default.
    :return: Document with identity members when a local key exists.
    :raises ValueError: If the default is unresolvable or a present seed is unreadable.
    """

    seed = identity_seed(seed_path)
    if seed is None:
        return dict(document)
    body = {
        **{name: value for name, value in document.items() if name != IDENTITY_SIGNATURE_MEMBER},
        IDENTITY_KEY_MEMBER: "ed25519:" + base64.b64encode(ed25519_public_key(seed)).decode("ascii"),
    }
    signature = ed25519_sign(seed, signature_digest(body))
    return {**body, IDENTITY_SIGNATURE_MEMBER: base64.b64encode(signature).decode("ascii")}


@dataclass(frozen=True)
class DocumentSignature:
    """Report what checking one document's optional identity signature established.

    :param present: Whether the document carried a signature block.
    :param valid: Whether the carried signature verified.
    :param operator_key: Encoded key from the signature, when present.
    :param reason: Explanation when the signature is absent or invalid.
    """

    present: bool
    valid: bool
    operator_key: str | None = None
    reason: str | None = None


def verify_document(document: Mapping[str, object]) -> DocumentSignature:
    """Check the optional identity signature of *document*.

    An absent signature is reported as absent rather than as a failure, so a
    document published by an installation without an identity key stays usable.
    A signature that is present and does not verify is a failure: it is either
    damaged or forged, and neither is something to act on.

    :param document: Document whose optional signature is checked.
    :return: Signature presence and verification result.
    """

    key = document.get(IDENTITY_KEY_MEMBER)
    signature = document.get(IDENTITY_SIGNATURE_MEMBER)
    if key is None and signature is None:
        return DocumentSignature(False, False)
    if not isinstance(key, str) or not isinstance(signature, str):
        return DocumentSignature(True, False, reason="the signature block is incomplete")
    text = key.removeprefix("ed25519:") if key.startswith("ed25519:") else key
    try:
        public_key = base64.b64decode(text, validate=True)
        raw_signature = base64.b64decode(signature, validate=True)
    except ValueError:
        return DocumentSignature(True, False, key, "the signature block is not valid base64")
    if len(public_key) != 32:
        return DocumentSignature(True, False, key, "the operator key is not a 32-byte Ed25519 key")
    if not ed25519_verify(public_key, signature_digest(document), raw_signature):
        return DocumentSignature(True, False, key, "the signature does not verify against the document")
    return DocumentSignature(True, True, key)
