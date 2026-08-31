"""The deterministic, signed project manifest.

A *manifest* is a signed record of every file in a project tree at one moment:
the same canonical, sorted record list a seal is built from, wrapped in a v2
JSONL.bz2 document with a domain-separated Ed25519 signature over its body. A
manifest covers the whole tree minus what each member decides to leave out of
its own internals, so payloads stay covered while working scratch does not.

Verification answers the two questions a signature always raises separately —
*does this manifest still describe this tree* (the digests and signature) and
*was it made by a key this project pins* (a trust anchor that never comes from
the manifest itself).
"""

import base64
import bz2
import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from .._json import json_bytes
from ..crypto import ed25519_public_key, ed25519_sign, ed25519_verify
from ..records import file_records
from ..register.members import project_member_handler
from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    canonical_public_key,
    format_public_key,
    key_fingerprint,
    read_project,
    read_public_key_file,
    require_project,
    trusted_project_keys,
)
from .members import project_members

__all__ = [
    "DEFAULT_MANIFEST_EXCLUSIONS",
    "INVALID",
    "VALID_TRUSTED",
    "VALID_UNKNOWN_KEY",
    "VERDICT_EXIT_CODES",
    "ManifestVerification",
    "create_manifest",
    "project_exclusions",
    "resolve_trusted_keys",
    "verify_manifest",
]

_DOMAIN = b"httk-project-manifest-v2\0"

#: The signature verified and the signing key is a pinned trust anchor.
VALID_TRUSTED = "valid_trusted"
#: The signature verified, but nothing pins the key that made it.
VALID_UNKNOWN_KEY = "valid_unknown_key"
#: The manifest does not describe this tree, or its signature does not verify.
INVALID = "invalid"

#: What the command line exits with for each verdict.
VERDICT_EXIT_CODES = {VALID_TRUSTED: 0, VALID_UNKNOWN_KEY: 3, INVALID: 1}

#: The exclusions every project manifest applies before its members contribute
#: their own. These keep out the anchor material a manifest cannot cover — the
#: trust anchors it would authenticate, the private keys, remote credentials,
#: and the manifest file itself — plus a stale pre-release ``.httk-project``.
DEFAULT_MANIFEST_EXCLUSIONS = (
    f"{PROJECT_DIRECTORY}/{PROJECT_FILE}",
    f"{PROJECT_DIRECTORY}/keys/*.seed",
    f"{PROJECT_DIRECTORY}/keys/*.priv",
    f"{PROJECT_DIRECTORY}/remotes/**/credentials*",
    f"{PROJECT_DIRECTORY}/launchers/**/credentials*",
    f"{PROJECT_DIRECTORY}/computers/**/credentials*",
    f"{PROJECT_DIRECTORY}/manifest.jsonl.bz2",
    f"{PROJECT_DIRECTORY}/seal.json",
    ".httk-project/project.json",
    ".httk-project/keys/*.seed",
    ".httk-project/keys/*.priv",
    ".httk-project/remotes/**/credentials*",
    ".httk-project/launchers/**/credentials*",
    ".httk-project/computers/**/credentials*",
    ".httk-project/manifest.jsonl.bz2",
)


def project_exclusions(metadata: dict[str, object]) -> tuple[str, ...]:
    """Return the default manifest exclusions plus the project's configured ones.

    :param metadata: Project metadata carrying the optional exclusion member.
    :return: The exclusion patterns applied before members contribute their own.
    :raises ValueError: If ``manifest_exclusions`` is not an array of strings.
    """

    configured = metadata.get("manifest_exclusions", [])
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        raise ValueError("manifest_exclusions must be an array of strings")
    return (*DEFAULT_MANIFEST_EXCLUSIONS, *(str(item) for item in configured))


def _project_seed(project: Path) -> bytes:
    """Return the project's raw 32-byte Ed25519 signing seed."""

    path = project / PROJECT_DIRECTORY / "keys" / "project.seed"
    try:
        seed = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read project signing seed: {path}") from exc
    if len(seed) != 32:
        raise ValueError("project private key is not a standard 32-byte Ed25519 seed")
    return seed


def _member_exclusions(root: Path) -> tuple[str, ...]:
    """Return every registered member's manifest exclusions, skipping absent kinds."""

    patterns: list[str] = []
    for member in project_members(root):
        try:
            handler = project_member_handler(member.kind)
        except LookupError:
            # A member whose module is not installed cannot describe its own
            # internals, so nothing of it is excluded: it is covered in full.
            continue
        patterns.extend(handler.manifest_exclusions(root, member.path))
    return tuple(patterns)


@contextlib.contextmanager
def _member_guards(root: Path) -> Iterator[None]:
    """Hold every installed member's snapshot guard around the manifest build."""

    with contextlib.ExitStack() as stack:
        for member in project_members(root):
            try:
                handler = project_member_handler(member.kind)
            except LookupError:
                continue
            stack.enter_context(handler.guard(root / member.path))
        yield


def create_manifest(
    project: str | os.PathLike[str] | None = None,
    *,
    output: str | os.PathLike[str] | None = None,
) -> Path:
    """Create and atomically publish the signed v2 project manifest.

    :param project: Locate the project to snapshot, or use discovery when unset.
    :param output: Publish the manifest at this path, or use the project default.
    :return: The published manifest path.
    :raises ValueError: If the project is invalid or cannot be snapshotted.
    """

    root = require_project(project)
    metadata = read_project(root)
    destination = (
        Path(output).expanduser().resolve() if output is not None else root / PROJECT_DIRECTORY / "manifest.jsonl.bz2"
    )
    exclusions = project_exclusions(metadata)
    if destination.is_relative_to(root):
        exclusions = (*exclusions, destination.relative_to(root).as_posix())
    with _member_guards(root):
        exclusions = (*exclusions, *_member_exclusions(root))
        seed = _project_seed(root)
        header = {
            "format": "httk-project-manifest",
            "format_version": 2,
            "project_id": metadata["project_id"],
            "hash": "sha256",
            "signature": "ed25519",
            "public_key": base64.b64encode(ed25519_public_key(seed)).decode("ascii"),
            "exclusions": list(exclusions),
        }
        body = b"".join(json_bytes(record) + b"\n" for record in (header, *file_records(root, exclusions=exclusions)))
        body_digest = hashlib.sha256(_DOMAIN + body).digest()
        trailer = {
            "body_sha256": body_digest.hex(),
            "signature": base64.b64encode(ed25519_sign(seed, body_digest)).decode("ascii"),
        }
        compressed = bz2.compress(body + json_bytes(trailer) + b"\n", compresslevel=9)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.tmp.", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(compressed)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def _parse_v2(path: Path) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object], bytes]:
    try:
        raw = bz2.decompress(path.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError(f"cannot decompress manifest: {path}") from exc
    lines = raw.splitlines(keepends=True)
    if len(lines) < 2 or any(not line.endswith(b"\n") for line in lines):
        raise ValueError("manifest must contain complete canonical JSON lines")
    values: list[dict[str, object]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("manifest contains invalid JSON") from exc
        if not isinstance(value, dict) or json_bytes(value) + b"\n" != line:
            raise ValueError("manifest line is not canonical JSON")
        values.append(value)
    header, trailer = values[0], values[-1]
    if header.get("format") != "httk-project-manifest" or header.get("format_version") != 2:
        raise ValueError("not a v2 httk project manifest")
    return header, values[1:-1], trailer, b"".join(lines[:-1])


@dataclass(frozen=True)
class ManifestVerification:
    """What verifying one manifest against one tree established.

    A signature check answers two separate questions. *Does this manifest
    describe this tree, unaltered?* is answered by the digests and the signature.
    *Was it made by somebody this project trusts?* is answered only by comparing
    the signing key with a trust anchor that did not come from the manifest.

    :param verdict: Classify the verification result.
    :param reason: Explain the classification.
    :param manifest: Identify the verified manifest.
    :param manifest_format: Identify the manifest format used.
    :param public_key: Record the signing key, when readable.
    :param trusted_keys: Record the trust anchors consulted.
    """

    verdict: str
    reason: str
    manifest: Path
    manifest_format: str
    public_key: str | None = None
    trusted_keys: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        """Whether the manifest describes this tree and its signature verified."""

        return self.verdict in {VALID_TRUSTED, VALID_UNKNOWN_KEY}

    @property
    def trusted(self) -> bool:
        """Whether the verified signature was made by a pinned key."""

        return self.verdict == VALID_TRUSTED

    @property
    def exit_code(self) -> int:
        """The command-line status this verdict reports."""

        return VERDICT_EXIT_CODES[self.verdict]

    def __bool__(self) -> bool:
        """A verification is truthy only when it is valid *and* trusted."""

        return self.trusted

    def as_mapping(self) -> dict[str, object]:
        """Return the JSON representation of this verdict.

        :return: JSON-compatible verification members.
        """

        return {
            "format": "httk-project-manifest-verification",
            "format_version": 2,
            "verdict": self.verdict,
            "reason": self.reason,
            "manifest": str(self.manifest),
            "manifest_format": self.manifest_format,
            "public_key": self.public_key,
            "trusted_keys": list(self.trusted_keys),
        }


def resolve_trusted_keys(
    project: str | os.PathLike[str] | None = None,
    *,
    trusted_keys: Sequence[str | os.PathLike[str]] | None = None,
) -> tuple[str, ...]:
    """Return the trust anchors of *project* plus every explicitly named key.

    An entry of *trusted_keys* is either a recorded key — ``ed25519:BASE64`` or
    the bare base64 — or the path of a ``*.pub`` file holding one.

    :param project: Locate the project whose pinned keys to include.
    :param trusted_keys: Add explicit recorded keys or public-key files.
    :return: Unique canonical trust-anchor values in stable order.
    :raises ValueError: If an explicit key cannot be canonicalized.
    """

    keys: list[str] = []
    if project is not None:
        try:
            metadata = read_project(project)
        except (OSError, ValueError):
            metadata = {}
        keys.extend(trusted_project_keys(metadata))
    for supplied in trusted_keys or ():
        text = str(supplied)
        candidate = Path(text).expanduser()
        recorded = read_public_key_file(candidate) if candidate.is_file() else canonical_public_key(text)
        if recorded not in keys:
            keys.append(recorded)
    return tuple(keys)


def _verdict_for_key(
    public_key: str,
    trusted: Sequence[str],
    *,
    manifest: Path,
    manifest_format: str,
) -> ManifestVerification:
    """Classify a verified signature against the trust anchors of a project."""

    if public_key in trusted:
        return ManifestVerification(
            VALID_TRUSTED,
            f"signed by the pinned project key {key_fingerprint(public_key)}",
            manifest,
            manifest_format,
            public_key,
            tuple(trusted),
        )
    if not trusted:
        reason = (
            "the signature verifies, but this project pins no key to check it against: "
            "the signing seed lives inside the tree, so anybody who can write the tree can "
            "re-sign it. Adopt the current key with pin_project_key(), or pass the key you "
            "expect explicitly"
        )
    else:
        reason = (
            f"the signature verifies, but it was made by {key_fingerprint(public_key)}, "
            "which is not among this project's trusted keys"
        )
    return ManifestVerification(
        VALID_UNKNOWN_KEY,
        reason,
        manifest,
        manifest_format,
        public_key,
        tuple(trusted),
    )


def _verify_v2(root: Path, path: Path, trusted: Sequence[str]) -> ManifestVerification:
    """Verify one v2 manifest against *root* and classify its signing key."""

    header, records, trailer, body = _parse_v2(path)
    exclusions = header.get("exclusions")
    if not isinstance(exclusions, list) or not all(isinstance(item, str) for item in exclusions):
        raise ValueError("manifest exclusions must be an array of strings")
    invalid = partial(ManifestVerification, INVALID, manifest=path, manifest_format="v2")
    digest = hashlib.sha256(_DOMAIN + body).digest()
    if trailer.get("body_sha256") != digest.hex():
        return invalid(reason="the manifest body does not match its own recorded digest")
    try:
        public_key = base64.b64decode(str(header["public_key"]), validate=True)
        signature = base64.b64decode(str(trailer["signature"]), validate=True)
    except (KeyError, ValueError):
        return invalid(reason="the manifest header or trailer has no readable key or signature")
    if len(public_key) != 32 or not ed25519_verify(public_key, digest, signature):
        return invalid(reason="the manifest signature does not verify")
    recorded = format_public_key(public_key)
    # The identity of the project is part of what a manifest claims: a manifest
    # made for another project, dropped into this tree, must never be reported as
    # this project's however well it verifies.
    if (root / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        expected = str(read_project(root).get("project_id", ""))
        found = str(header.get("project_id", ""))
        if expected and found != expected:
            return invalid(
                reason=f"the manifest names project {found or 'nothing'}, but this project is {expected}",
                public_key=recorded,
                trusted_keys=tuple(trusted),
            )
    if records != list(file_records(root, exclusions=exclusions)):
        return invalid(
            reason="the tree does not match the manifest",
            public_key=recorded,
            trusted_keys=tuple(trusted),
        )
    return _verdict_for_key(recorded, trusted, manifest=path, manifest_format="v2")


def verify_manifest(
    project: str | os.PathLike[str] | None = None,
    *,
    manifest: str | os.PathLike[str] | None = None,
    trusted_keys: Sequence[str | os.PathLike[str]] | None = None,
) -> ManifestVerification:
    """Verify a project's v2 manifest against the tree and its trust anchors.

    The trust anchor is the key pinned in ``project.json`` — never the key the
    manifest names in its own header — plus any key passed in *trusted_keys*, as
    a recorded value or the path of a ``*.pub`` file.

    :param project: Locate the project to discover and verify.
    :param manifest: Select a manifest path instead of the project default.
    :param trusted_keys: Add explicit trust anchors to the project keys.
    :return: The detailed verification verdict.
    :raises ValueError: If no project or usable manifest exists.
    :raises FileNotFoundError: If the selected manifest file is absent.
    """

    root = require_project(project)
    trusted = resolve_trusted_keys(root, trusted_keys=trusted_keys)
    path = (
        Path(manifest).expanduser().resolve()
        if manifest is not None
        else root / PROJECT_DIRECTORY / "manifest.jsonl.bz2"
    )
    if not path.is_file():
        raise FileNotFoundError(path)
    return _verify_v2(root, path, trusted)
