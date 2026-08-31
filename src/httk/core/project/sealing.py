"""Write, read, sign, and verify project seal documents.

A *seal* is a signed statement of what a subject contained at one moment. A
project seal records the project's loose files and, for every registered member,
the digest of that member's own seal, so a project seal transitively pins whole
member subtrees without re-hashing them: a change to any covered byte becomes a
discrepancy the moment the seal is verified.

The signature is over a domain-separated digest of the document body, exactly as
a signed project manifest is signed, so a digest signed as a seal can never be
replayed as anything else. Verification answers the two independent questions a
signature always raises separately — does the seal still describe this subject,
and was it made by a key this project trusts — and reports both.
"""

import base64
import hashlib
import json
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from .._json import json_bytes, write_json_atomic
from ..crypto import ed25519_public_key, ed25519_sign, ed25519_verify
from ..identity import identity_key_paths, identity_seed
from ..records import file_records
from ..register.members import project_member_handler
from .anchor import (
    PROJECT_DIRECTORY,
    canonical_public_key,
    discover_project,
    format_public_key,
    key_fingerprint,
    parse_public_key,
    read_project,
)
from .manifests import _project_seed, project_exclusions
from .members import project_members

__all__ = [
    "INVALID",
    "VALID_TRUSTED",
    "VALID_UNKNOWN_KEY",
    "Discrepancy",
    "Seal",
    "SealError",
    "SealKey",
    "SealKeys",
    "SealReport",
    "SealVerification",
    "SealedError",
    "build_seal_body",
    "default_project_keys",
    "diff_records",
    "is_project_sealed",
    "normalize_trusted_keys",
    "project_seal_path",
    "read_seal",
    "resolve_seal_keys",
    "seal_project",
    "sign_seal_body",
    "unseal_project",
    "verify_project",
    "verify_seal",
    "write_seal",
]

_LOGGER = logging.getLogger(__name__)

#: Domain separation of every seal signature, so a seal digest is never a valid
#: signature of a manifest, an identity document, or any other httk artifact.
_DOMAIN = b"httk-seal-v1\0"

_FORMAT = "httk-seal"
_FORMAT_VERSION = 1

#: The signing roles a seal understands.
ROLE_PROJECT = "project"
ROLE_IDENTITY = "identity"
ROLE_FILE = "file"

#: The seal signature verified and a signer is a pinned trust anchor.
VALID_TRUSTED = "valid_trusted"
#: The seal signature verified, but nothing pins the key that made it.
VALID_UNKNOWN_KEY = "valid_unknown_key"
#: The seal does not describe this subject, or a signature does not verify.
INVALID = "invalid"

#: One resolved signing key: its role and its raw 32-byte Ed25519 seed.
SealKey = tuple[str, bytes]

#: The members of a seal document that make up the signed body.
_BODY_MEMBERS = ("format", "format_version", "kind", "subject", "created_at", "records")


class SealError(RuntimeError):
    """A seal cannot be written or verified.

    This is the *cannot proceed* failure: no signing key is available, or a
    member a project seal must cover is itself unsealed or has no handler. It
    never means an action was refused because something was already sealed; that
    is :class:`SealedError`.
    """


class SealedError(RuntimeError):
    """An action was refused because the subject, or its enclosure, is sealed.

    Changing a project's members while the project is sealed is refused rather
    than silently allowed: a seal a project commits to must not change beneath
    it.
    """


@dataclass(frozen=True)
class SealKeys:
    """The signing keys resolved for one seal, and the roles that were missing.

    :param keys: The available signing keys, in the order their refs resolved.
    :param missing_roles: The roles requested but which could not be resolved.
    """

    keys: tuple[SealKey, ...]
    missing_roles: tuple[str, ...]


@dataclass(frozen=True)
class Discrepancy:
    """One way a sealed subject no longer matches its seal.

    :param path: The record path or member relpath that disagrees.
    :param kind: The disagreement: ``missing``, ``extra``, ``mismatch``,
        ``unsealed`` (present but not recorded), or ``missing_job`` (recorded but
        absent).
    """

    path: str
    kind: str


@dataclass(frozen=True)
class Seal:
    """One parsed seal document.

    :param kind: The sealed level (``project`` for a project seal).
    :param subject: The identifiers of the sealed subject.
    :param created_at: When the seal was written.
    :param records: The recorded contents of the sealed subject.
    :param body_sha256: The recorded digest of the signed body.
    :param signatures: The detached signatures over the body digest.
    :param body_bytes: The canonical bytes the recorded digest is taken over.
    :param path: Where the seal was read from.
    """

    kind: str
    subject: dict[str, object]
    created_at: str
    records: tuple[dict[str, object], ...]
    body_sha256: str
    signatures: tuple[dict[str, object], ...]
    body_bytes: bytes
    path: Path


@dataclass(frozen=True)
class SealVerification:
    """What verifying one seal established.

    :param valid: Whether the seal describes its subject and a signature verified.
    :param verdict: One of ``VALID_TRUSTED``, ``VALID_UNKNOWN_KEY``, or
        ``INVALID``.
    :param reason: A human-readable explanation of the verdict.
    :param signers: The fingerprints of the signatures that verified.
    :param missing_signers: The expected roles that the seal did not carry.
    :param discrepancies: How the subject diverges from the seal, if at all.
    """

    valid: bool
    verdict: str
    reason: str
    signers: tuple[str, ...]
    missing_signers: tuple[str, ...]
    discrepancies: tuple[Discrepancy, ...]

    def as_entry(self, level: str, subject: str) -> dict[str, object]:
        """Return this verdict as one whole-tree report entry.

        :param level: The subject level this verdict is for.
        :param subject: The subject identifier this verdict is for.
        :return: The JSON-compatible report entry.
        """

        return {
            "level": level,
            "subject": subject,
            "valid": self.valid,
            "verdict": self.verdict,
            "reason": self.reason,
            "signers": list(self.signers),
            "missing_signers": list(self.missing_signers),
            "discrepancies": [{"kind": item.kind, "path": item.path} for item in self.discrepancies],
        }


@dataclass(frozen=True)
class SealReport:
    """The verdicts of verifying a seal and, when deep, every seal below it.

    :param entries: A flat sequence of report-entry mappings, parent before
        child, each in the shape :meth:`SealVerification.as_entry` produces.
    :param ok: Whether every entry is valid and at least one entry exists.
    """

    entries: tuple[dict[str, object], ...]
    ok: bool


# -- locations ---------------------------------------------------------------


def project_seal_path(project_root: str | os.PathLike[str]) -> Path:
    """Return where one project's seal lives.

    :param project_root: The project root whose seal path to build.
    :return: The project seal path.
    """

    return Path(project_root).expanduser().resolve() / PROJECT_DIRECTORY / "seal.json"


def is_project_sealed(project_root: str | os.PathLike[str]) -> bool:
    """Return whether one project carries a seal.

    :param project_root: The project root to check.
    :return: Whether the project seal file exists.
    """

    return project_seal_path(project_root).is_file()


# -- keys --------------------------------------------------------------------


def _role_of(ref: str) -> str:
    """Classify one key ref into the role its signature carries."""

    if ref == ROLE_PROJECT:
        return ROLE_PROJECT
    if ref == ROLE_IDENTITY or ref.startswith("identity:"):
        return ROLE_IDENTITY
    return ROLE_FILE


def _seed_for_ref(ref: str, project_root: Path) -> bytes | None:
    """Resolve one key ref to a seed, or ``None`` when it is unavailable."""

    if ref == ROLE_PROJECT:
        project = discover_project(project_root)
        if project is None:
            return None
        try:
            return _project_seed(project)
        except ValueError:
            return None
    if ref == ROLE_IDENTITY:
        return identity_seed()
    if ref.startswith("identity:"):
        short = ref[len("identity:") :]
        try:
            seed_path = identity_key_paths(short)[0]
        except ValueError:
            return None
        return identity_seed(seed_path)
    path = Path(ref).expanduser()
    try:
        seed = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except (OSError, ValueError):
        return None
    return seed if len(seed) == 32 else None


def resolve_seal_keys(refs: Sequence[str], *, project_root: str | os.PathLike[str]) -> SealKeys:
    """Resolve seal-key refs to the signing keys that are actually available.

    A ref is ``project`` (the project's own signing seed, discovered from
    *project_root*), ``identity`` (the default operator identity),
    ``identity:<short>`` (a named identity), or the path of a base64 Ed25519 seed
    file. An unavailable ref is skipped and logged rather than fatal; only
    resolving no key at all is an error.

    :param refs: The key refs to resolve, in order.
    :param project_root: The tree the ``project`` ref is discovered from.
    :return: The resolved keys and the roles that could not be resolved.
    :raises SealError: If no key at all could be resolved.
    """

    root = Path(project_root).expanduser().resolve()
    keys: list[SealKey] = []
    missing: list[str] = []
    for ref in refs:
        role = _role_of(ref)
        seed = _seed_for_ref(ref, root)
        if seed is None:
            missing.append(role)
            _LOGGER.info(
                "seal key %r is unavailable and will not sign",
                ref,
                extra={"event": "seal_key_unavailable", "ref": ref},
            )
            continue
        keys.append((role, seed))
    if not keys:
        raise SealError(f"no seal signing key could be resolved from {list(refs)}")
    return SealKeys(tuple(keys), tuple(missing))


def default_project_keys(root: str | os.PathLike[str], refs: Sequence[str] | None = None) -> SealKeys:
    """Resolve a project's signing keys from its ``seal_keys`` member or *refs*.

    :param root: The project root whose ``seal_keys`` member is read.
    :param refs: Key refs to use instead of the project member, when given.
    :return: The resolved signing keys and the roles that could not be resolved.
    :raises SealError: If the member is malformed or no key resolves.
    """

    if refs is None:
        raw = read_project(root).get("seal_keys", [ROLE_PROJECT, ROLE_IDENTITY])
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise SealError("project member 'seal_keys' must be an array of strings")
        refs = [str(item) for item in raw]
    return resolve_seal_keys(refs, project_root=root)


# -- writing -----------------------------------------------------------------


def build_seal_body(
    kind: str, subject: Mapping[str, object], records: Sequence[dict[str, object]]
) -> dict[str, object]:
    """Assemble the signed body of one seal document.

    The returned mapping is the exact, canonical body a signature is taken over
    — its ``created_at`` is stamped now — so a caller signs and writes it with
    :func:`sign_seal_body` and :func:`write_seal`.

    :param kind: The sealed level, such as ``project`` or a member kind.
    :param subject: The identifiers of the sealed subject.
    :param records: The recorded contents of the sealed subject.
    :return: The unsigned seal body.
    """

    return {
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "kind": kind,
        "subject": dict(subject),
        "created_at": _utc_now(),
        "records": list(records),
    }


def _utc_now() -> str:
    """Return the current UTC time as a stable ISO-8601 string with ``Z``."""

    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign_seal_body(body: dict[str, object], keys: Sequence[SealKey]) -> tuple[str, list[dict[str, object]]]:
    """Digest a seal body and produce one detached signature per key.

    :param body: The seal body from :func:`build_seal_body`.
    :param keys: The signing keys, each a ``(role, seed)`` pair.
    :return: The hex body digest and the detached signatures.
    """

    body_digest = hashlib.sha256(_DOMAIN + json_bytes(body)).digest()
    message = _DOMAIN + body_digest
    signatures: list[dict[str, object]] = []
    for role, seed in keys:
        key = format_public_key(ed25519_public_key(seed))
        signatures.append(
            {
                "role": role,
                "key": key,
                "fingerprint": key_fingerprint(key),
                "signature": base64.b64encode(ed25519_sign(seed, message)).decode("ascii"),
            }
        )
    return body_digest.hex(), signatures


def write_seal(path: Path, body: dict[str, object], keys: Sequence[SealKey]) -> Path:
    """Sign a seal body and write the seal document atomically.

    :param path: Where to write the seal document.
    :param body: The seal body from :func:`build_seal_body`.
    :param keys: The signing keys, each a ``(role, seed)`` pair.
    :return: The written seal path.
    :raises SealError: If no signing key is available.
    """

    if not keys:
        raise SealError(f"no signing key is available to seal the {body.get('kind')}")
    body_sha256, signatures = sign_seal_body(body, keys)
    document = {**body, "body_sha256": body_sha256, "signatures": signatures}
    write_json_atomic(path, document, durable=True)
    return path


# -- reading and signature verification --------------------------------------


def read_seal(path: str | os.PathLike[str]) -> Seal:
    """Read and structurally validate one seal document.

    :param path: The seal file to read.
    :return: The parsed seal.
    :raises ValueError: If the file is not a valid seal document.
    :raises OSError: If the file cannot be read.
    """

    location = Path(path)
    try:
        document = json.loads(location.read_bytes())
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"seal is not valid JSON: {location}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"seal is not a JSON object: {location}")
    if document.get("format") != _FORMAT or document.get("format_version") != _FORMAT_VERSION:
        raise ValueError(f"not an {_FORMAT} version {_FORMAT_VERSION} document: {location}")
    try:
        body = {member: document[member] for member in _BODY_MEMBERS}
    except KeyError as exc:
        raise ValueError(f"seal is missing member {exc.args[0]!r}: {location}") from exc
    subject = document["subject"]
    records = document["records"]
    signatures = document["signatures"]
    body_sha256 = document["body_sha256"]
    if (
        not isinstance(subject, dict)
        or not isinstance(records, list)
        or not isinstance(signatures, list)
        or not isinstance(body_sha256, str)
        or not all(isinstance(item, dict) for item in records)
        or not all(isinstance(item, dict) for item in signatures)
    ):
        raise ValueError(f"seal has a malformed body: {location}")
    return Seal(
        kind=str(document["kind"]),
        subject=subject,
        created_at=str(document["created_at"]),
        records=tuple(records),
        body_sha256=body_sha256,
        signatures=tuple(signatures),
        body_bytes=json_bytes(body),
        path=location,
    )


def normalize_trusted_keys(trusted_keys: Iterable[str]) -> set[str]:
    """Return trust anchors as canonical keys and fingerprints, skipping junk.

    :param trusted_keys: Trust anchors as ``ed25519:`` keys or ``sha256:`` fingerprints.
    :return: The canonical keys and fingerprints, with unparseable entries dropped.
    """

    result: set[str] = set()
    for entry in trusted_keys:
        text = str(entry).strip()
        if text.startswith("sha256:"):
            result.add(text)
            continue
        try:
            result.add(canonical_public_key(text))
        except ValueError:
            continue
    return result


def verify_seal(
    path: str | os.PathLike[str],
    *,
    trusted_keys: Iterable[str] = (),
    expected_roles: Iterable[str] = (),
) -> SealVerification:
    """Verify one seal's body digest and signatures, and classify the signers.

    This checks the seal against itself, not against the subject: at least one
    signature must verify, any signature that does not makes the seal invalid,
    and the seal is trusted when a verifying signer is a pinned key or
    fingerprint. Subject-level checks are done by :func:`verify_project`.

    :param path: The seal file to verify.
    :param trusted_keys: Trust anchors as ``ed25519:`` keys or ``sha256:`` fingerprints.
    :param expected_roles: Signing roles the seal is expected to carry.
    :return: The signature verdict.
    :raises ValueError: If the file is not a valid seal document.
    :raises OSError: If the file cannot be read.
    """

    seal = read_seal(path)
    expected = tuple(expected_roles)
    present_roles = {str(signature.get("role")) for signature in seal.signatures}
    missing = tuple(role for role in expected if role not in present_roles)
    if hashlib.sha256(_DOMAIN + seal.body_bytes).hexdigest() != seal.body_sha256:
        return SealVerification(False, INVALID, "the seal body does not match its recorded digest", (), missing, ())
    try:
        message = _DOMAIN + bytes.fromhex(seal.body_sha256)
    except ValueError:
        return SealVerification(False, INVALID, "the seal's recorded digest is not hex", (), missing, ())
    trusted = normalize_trusted_keys(trusted_keys)
    signers: list[str] = []
    any_invalid = False
    any_trusted = False
    for signature in seal.signatures:
        key = signature.get("key")
        raw = signature.get("signature")
        if not isinstance(key, str) or not isinstance(raw, str):
            any_invalid = True
            continue
        try:
            public_key = parse_public_key(key)
            signature_bytes = base64.b64decode(raw, validate=True)
        except ValueError:
            any_invalid = True
            continue
        if len(public_key) != 32 or not ed25519_verify(public_key, message, signature_bytes):
            any_invalid = True
            continue
        canonical = format_public_key(public_key)
        fingerprint = key_fingerprint(canonical)
        signers.append(fingerprint)
        if canonical in trusted or fingerprint in trusted:
            any_trusted = True
    if any_invalid:
        return SealVerification(False, INVALID, "a seal signature does not verify", tuple(signers), missing, ())
    if not signers:
        return SealVerification(False, INVALID, "the seal carries no signature", (), missing, ())
    if any_trusted:
        return SealVerification(True, VALID_TRUSTED, "signed by a trusted key", tuple(signers), missing, ())
    return SealVerification(
        True, VALID_UNKNOWN_KEY, "the signature verifies but no signer is trusted", tuple(signers), missing, ()
    )


# -- record checks -----------------------------------------------------------


def _combine(base: SealVerification, discrepancies: Sequence[Discrepancy]) -> SealVerification:
    """Fold record discrepancies into a signature verdict."""

    if not discrepancies:
        return base
    reason = base.reason if base.verdict == INVALID else "the sealed subject no longer matches the seal"
    return replace(base, valid=False, verdict=INVALID, reason=reason, discrepancies=tuple(discrepancies))


def diff_records(recorded: Sequence[dict[str, object]], actual: Sequence[dict[str, object]]) -> list[Discrepancy]:
    """Diff two path-keyed record lists into discrepancies.

    :param recorded: The records a seal recorded.
    :param actual: The records the tree holds now.
    :return: The per-path discrepancies, sorted by path.
    """

    recorded_by_path = {str(record["path"]): record for record in recorded}
    actual_by_path = {str(record["path"]): record for record in actual}
    discrepancies: list[Discrepancy] = []
    for relpath in sorted(set(recorded_by_path) | set(actual_by_path)):
        if relpath not in actual_by_path:
            discrepancies.append(Discrepancy(relpath, "missing"))
        elif relpath not in recorded_by_path:
            discrepancies.append(Discrepancy(relpath, "extra"))
        elif recorded_by_path[relpath] != actual_by_path[relpath]:
            discrepancies.append(Discrepancy(relpath, "mismatch"))
    return discrepancies


# -- project seals -----------------------------------------------------------


def _seal_exclusions(root: Path, metadata: dict[str, object]) -> tuple[str, ...]:
    """Return the loose-file exclusions of a project seal.

    A project seal's loose files are everything the manifest defaults exclude,
    plus each member's own manifest exclusions, plus each member's whole subtree
    — the subtree is covered through the member's seal digest rather than
    re-hashed here.
    """

    patterns: list[str] = list(project_exclusions(metadata))
    for member in project_members(root):
        try:
            handler = project_member_handler(member.kind)
        except LookupError:
            continue
        patterns.extend(handler.manifest_exclusions(root, member.path))
        # ponytail: a member registered at "." shares the project tree, so this
        # subtree exclusion is a no-op for it; the root-as-member layout is a
        # workflow concern handled through that handler's manifest_exclusions.
        patterns.extend((member.path, f"{member.path}/**"))
    return tuple(patterns)


def seal_project(project_root: str | os.PathLike[str], *, keys: SealKeys | None = None) -> Path:
    """Seal a project's loose files and every member's seal digest.

    Every registered member must already be sealed, and every member kind must
    have a registered handler; otherwise the project cannot be sealed.

    :param project_root: The project root to seal.
    :param keys: The signing keys, or ``None`` to use the project default.
    :return: The project seal path.
    :raises SealError: If a member is unsealed, a kind has no handler, or no key resolves.
    """

    root = Path(project_root).expanduser().resolve()
    metadata = read_project(root)
    members = sorted(project_members(root), key=lambda member: member.path)
    handlers = []
    for member in members:
        try:
            handlers.append((member, project_member_handler(member.kind)))
        except LookupError as exc:
            raise SealError(
                f"project member {member.path!r} has kind {member.kind!r} with no registered handler: {exc}"
            ) from exc
    member_records: list[dict[str, object]] = []
    unsealed: list[str] = []
    for member, handler in handlers:
        try:
            member_id, digest = handler.seal_digest(root / member.path)
        except SealError:
            unsealed.append(member.path)
            continue
        member_records.append({"member": member.path, "kind": member.kind, "id": member_id, "seal_sha256": digest})
    if unsealed:
        raise SealError(f"cannot seal the project while these members are unsealed: {', '.join(unsealed)}")
    exclusions = _seal_exclusions(root, metadata)
    records: list[dict[str, object]] = list(file_records(root, exclusions=exclusions))
    records.extend(member_records)
    resolved = keys if keys is not None else default_project_keys(root)
    subject = {"project_id": str(metadata["project_id"])}
    body = build_seal_body("project", subject, records)
    return write_seal(project_seal_path(root), body, resolved.keys)


def unseal_project(project_root: str | os.PathLike[str]) -> None:
    """Remove a project's seal.

    :param project_root: The project root to unseal.
    """

    project_seal_path(project_root).unlink(missing_ok=True)


def _verify_project_records(root: Path, seal: Seal, metadata: dict[str, object]) -> list[Discrepancy]:
    """Diff a project seal's loose files and member digests against the tree."""

    exclusions = _seal_exclusions(root, metadata)
    recorded_files = [record for record in seal.records if "type" in record]
    actual_files = file_records(root, exclusions=exclusions)
    discrepancies = diff_records(recorded_files, actual_files)
    recorded_members = {str(record["member"]): record for record in seal.records if "member" in record}
    present = {member.path: member for member in project_members(root)}
    for relpath in sorted(set(recorded_members) | set(present)):
        if relpath not in present:
            discrepancies.append(Discrepancy(relpath, "missing_job"))
        elif relpath not in recorded_members:
            discrepancies.append(Discrepancy(relpath, "unsealed"))
        else:
            try:
                handler = project_member_handler(present[relpath].kind)
                _member_id, digest = handler.seal_digest(root / relpath)
            except (LookupError, SealError, OSError):
                discrepancies.append(Discrepancy(relpath, "missing"))
            else:
                if digest != recorded_members[relpath]["seal_sha256"]:
                    discrepancies.append(Discrepancy(relpath, "mismatch"))
    return discrepancies


def verify_project(
    project_root: str | os.PathLike[str],
    *,
    trusted_keys: Iterable[str] = (),
    deep: bool = True,
) -> SealReport:
    """Verify a project's seal and, when deep, every member seal it references.

    :param project_root: The project root to verify.
    :param trusted_keys: Trust anchors to classify the signers against.
    :param deep: Whether to delegate to each member handler's own verification.
    :return: The flat report of every verdict, with an overall ``ok``.
    """

    root = Path(project_root).expanduser().resolve()
    trusted = tuple(str(key) for key in trusted_keys)
    subject = str(read_project(root).get("project_id", ""))
    if not is_project_sealed(root):
        verification = SealVerification(False, INVALID, "not sealed", (), (), ())
        return SealReport((verification.as_entry("project", subject),), False)
    metadata = read_project(root)
    base = verify_seal(project_seal_path(root), trusted_keys=trusted)
    seal = read_seal(project_seal_path(root))
    verification = _combine(base, _verify_project_records(root, seal, metadata))
    entries: list[dict[str, object]] = [verification.as_entry("project", subject)]
    if deep:
        for record in seal.records:
            if "member" not in record:
                continue
            relpath = str(record["member"])
            kind = str(record.get("kind", ""))
            try:
                handler = project_member_handler(kind)
            except LookupError:
                entries.append(
                    SealVerification(False, INVALID, f"no handler for kind {kind!r}", (), (), ()).as_entry(
                        "member", relpath
                    )
                )
                continue
            entries.extend(handler.verify(root / relpath, trusted_keys=trusted, deep=deep))
    ok = bool(entries) and all(bool(entry.get("valid")) for entry in entries)
    return SealReport(tuple(entries), ok)
