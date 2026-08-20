"""Create and verify signed, private-key-free project redistributions.

Path and suffix exclusions are the primary private-key protection.  The
content guard catches exact and re-encoded copies of known private material;
arbitrarily transformed or truncated secrets are outside its scope.
"""

import base64
import binascii
import hashlib
import json
import os
import tempfile
import zipfile
import zlib
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

from httk.core.crypto import ed25519_public_key, ed25519_sign, ed25519_verify
from httk.core.digests import tree_digest

from .anchor import (
    PROJECT_DIRECTORY,
    canonical_public_key,
    format_public_key,
    key_fingerprint,
    parse_public_key,
    pinned_project_key,
    project_public_key_path,
    read_public_key_file,
    require_project,
)

__all__ = ["PROJECT_PRIVATE_KEY_RELATIVE_PATH", "seal_project", "verify_seal"]

PROJECT_PRIVATE_KEY_RELATIVE_PATH = f"{PROJECT_DIRECTORY}/keys/project.seed"
"""The exact private-key path created by the project identity implementation."""

_PRIVATE_KEY_SUFFIXES = (".key", ".priv", ".seed")
_VCS_DIRECTORIES = frozenset({".bzr", ".git", ".hg", ".jj", ".svn"})


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_text(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"seal {label} must be a lowercase SHA-256 digest")
    return value


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _private_key_like(relative: str) -> bool:
    return PurePosixPath(relative).name.casefold().endswith(_PRIVATE_KEY_SUFFIXES)


def _v1_private_key(relative: str) -> bool:
    parts = tuple(part.casefold() for part in PurePosixPath(relative).parts)
    return len(parts) == 3 and parts[:2] == ("ht.project", "keys") and parts[2].endswith(".priv")


def _excluded(relative: str, output: str | None) -> bool:
    parts = PurePosixPath(relative).parts
    return (
        bool(parts and parts[0].casefold() in _VCS_DIRECTORIES)
        or relative == PROJECT_PRIVATE_KEY_RELATIVE_PATH
        or _v1_private_key(relative)
        or relative == output
    )


def _decoded_base64(data: bytes) -> bytes | None:
    try:
        compact = b"".join(data.split())
        if not compact:
            return None
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None


def _private_material(data: bytes) -> frozenset[bytes]:
    decoded = _decoded_base64(data)
    return frozenset((data, decoded) if decoded is not None else (data,))


def _inventory(project: Path, output: Path, private_material: frozenset[bytes]) -> tuple[list[Path], list[str]]:
    output_relative: str | None
    try:
        output_relative = _relative(output, project)
    except ValueError:
        output_relative = None
    files: list[Path] = []
    directories: list[str] = []
    for entry in sorted(project.rglob("*"), key=lambda item: _relative(item, project)):
        relative = _relative(entry, project)
        if _excluded(relative, output_relative):
            continue
        if _private_key_like(relative):
            raise ValueError(f"private-key-like file cannot be sealed: {relative}")
        if entry.is_symlink():
            raise ValueError(f"symlink is forbidden in immutable seal: {entry}")
        if entry.is_dir():
            directories.append(relative)
        elif entry.is_file():
            data = entry.read_bytes()
            decoded = _decoded_base64(data)
            if data in private_material or (decoded is not None and decoded in private_material):
                raise ValueError(f"file content matches a project private key: {relative}")
            files.append(entry)
        else:
            raise ValueError(f"special file is forbidden in immutable seal: {entry}")
    return files, directories


def _read_seed(project: Path) -> tuple[bytes, frozenset[bytes]]:
    path = project / PROJECT_PRIVATE_KEY_RELATIVE_PATH
    try:
        seed_file = path.read_bytes()
        seed = base64.b64decode(seed_file.decode("ascii").strip(), validate=True)
    except (OSError, UnicodeError, ValueError, binascii.Error) as error:
        raise ValueError(f"cannot read project signing key: {path}") from error
    if len(seed) != 32:
        raise ValueError(f"project signing key is not a 32-byte Ed25519 seed: {path}")
    public = format_public_key(ed25519_public_key(seed))
    if public != read_public_key_file(project_public_key_path(project)):
        raise ValueError("project private and public keys do not match")
    private_material = set(_private_material(seed_file))
    private_material.add(seed)
    for entry in project.rglob("*"):
        relative = _relative(entry, project)
        if _v1_private_key(relative) and entry.is_file():
            private_material.update(_private_material(entry.read_bytes()))
    return seed, frozenset(private_material)


def _reject_output_collision(project: Path, destination: Path) -> None:
    if destination == project:
        raise ValueError("seal output cannot be the project directory")
    if destination.exists():
        control = project / PROJECT_DIRECTORY
        for protected in control.rglob("*"):
            if protected.is_file():
                try:
                    if os.path.samefile(destination, protected):
                        raise ValueError(f"seal output collides with protected project data: {destination}")
                except OSError:
                    pass
    try:
        relative = destination.relative_to(project)
    except ValueError:
        return
    if relative.parts and relative.parts[0].casefold() == PROJECT_DIRECTORY.casefold():
        raise ValueError(f"seal output cannot be inside protected project data: {destination}")
    if destination.exists():
        raise ValueError(f"seal output already exists inside the project tree: {destination}")


def _zip_write(path: Path, entries: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.close(descriptor)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(entries):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                archive.writestr(info, entries[name])
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def seal_project(out_path: str | Path, project_path: str | Path | None = None) -> Path:
    """Create a signed ZIP containing a project without private keys.

    The path and suffix exclusions are primary.  The content guard catches
    exact and re-encoded copies of known private material; transformed or
    truncated secrets are outside that guard's scope.

    :param out_path: Destination ZIP path.
    :param project_path: Project root, or None to discover the nearest project.
    :return: The destination path.
    :raises ValueError: If the project is unsafe to seal or its identity is invalid.
    """

    project = require_project(project_path)
    destination = Path(out_path).expanduser().resolve()
    _reject_output_collision(project, destination)
    seed, private_hashes = _read_seed(project)
    files, directories = _inventory(project, destination, private_hashes)

    output_relative = _relative(destination, project) if destination.is_relative_to(project) else None
    excluded = lambda relative: _excluded(relative, output_relative)
    digest = tree_digest(project, exclude=excluded)
    payloads = {f"project/{_relative(path, project)}": path.read_bytes() for path in files}
    manifest = {
        "format": "httk-seal",
        "format_version": 2,
        "tree_digest": digest,
        "directories": directories,
        "files": [
            {"path": name.removeprefix("project/"), "sha256": _sha256(data)} for name, data in sorted(payloads.items())
        ],
    }
    manifest_bytes = _json_bytes(manifest)
    signature = {
        "algorithm": "Ed25519",
        "public_key": read_public_key_file(project_public_key_path(project)),
        "fingerprint": key_fingerprint(read_public_key_file(project_public_key_path(project))),
        "signature": base64.b64encode(ed25519_sign(seed, manifest_bytes)).decode("ascii"),
    }
    _zip_write(
        destination, {**payloads, "seal/manifest.json": manifest_bytes, "seal/signature": _json_bytes(signature)}
    )
    return destination


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name and not path.is_absolute() and ".." not in path.parts and "\\" not in name)


def _read_member(archive: zipfile.ZipFile, name: str, label: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as error:
        raise ValueError(f"missing seal {label}: {name}") from error
    except (zipfile.BadZipFile, EOFError, zlib.error) as error:
        raise ValueError(f"corrupt seal {label}: {name}") from error


def _fingerprint(value: str) -> str:
    if value.startswith("sha256:"):
        fingerprint = value.lower()
        _, _, hexadecimal = fingerprint.partition(":")
        if len(hexadecimal) != 64 or any(character not in "0123456789abcdef" for character in hexadecimal):
            raise ValueError(f"invalid key fingerprint: {value!r}")
        return fingerprint
    return key_fingerprint(value)


def verify_seal(
    zip_path: str | Path,
    *,
    expect_key: str | None = None,
    trusted_keys: Iterable[str] = (),
) -> dict[str, object]:
    """Verify a sealed project ZIP and return signer information.

    :param zip_path: Seal ZIP to verify.
    :param expect_key: Expected signer fingerprint or public key.
    :param trusted_keys: Trusted signer fingerprints or public keys.
    :return: A JSON-ready verification report.
    :raises ValueError: If the ZIP, manifest, files, tree digest, or signature is invalid.
    """

    path = Path(zip_path).expanduser().resolve()
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"invalid seal ZIP: {path}") from error
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not all(_safe_member(name) for name in names):
            raise ValueError("seal contains invalid or duplicate ZIP members")
        manifest_bytes = _read_member(archive, "seal/manifest.json", "manifest")
        signature_bytes = _read_member(archive, "seal/signature", "signature")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid seal manifest JSON") from error
        if not isinstance(manifest, dict):
            raise ValueError("seal manifest JSON must be an object")
        if (
            manifest.get("format") != "httk-seal"
            or type(manifest.get("format_version")) is not int
            or manifest["format_version"] != 2
        ):
            raise ValueError("unsupported seal format")
        manifest_tree_digest = _digest_text(manifest.get("tree_digest"), "manifest tree_digest")
        files = manifest.get("files")
        directories = manifest.get("directories", [])
        if (
            not isinstance(files, list)
            or not isinstance(directories, list)
            or not all(isinstance(directory, str) for directory in directories)
        ):
            raise ValueError("seal manifest file inventory is invalid")
        try:
            signature = json.loads(signature_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid seal signature JSON") from error
        if not isinstance(signature, dict):
            raise ValueError("seal signature JSON must be an object")
        if signature.get("algorithm") != "Ed25519":
            raise ValueError("unsupported seal signature algorithm")
        try:
            public_text = signature["public_key"]
            signature_text = signature["signature"]
            if not isinstance(public_text, str) or not isinstance(signature_text, str):
                raise ValueError("signature fields must be strings")
            public = parse_public_key(public_text)
            signed = base64.b64decode(signature_text, validate=True)
        except (KeyError, ValueError, binascii.Error) as error:
            raise ValueError("seal signature is malformed") from error
        metadata_bytes = _read_member(archive, "project/httk_project/project.json", "project metadata")
        public_file_bytes = _read_member(archive, "project/httk_project/keys/project.pub", "project public key")
        try:
            metadata = json.loads(metadata_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid bundled project metadata JSON") from error
        if not isinstance(metadata, Mapping):
            raise ValueError("bundled project metadata JSON must be an object")
        pinned = pinned_project_key(metadata)
        if pinned is None:
            raise ValueError("bundled project metadata has no pinned public key")
        try:
            bundled_public = canonical_public_key(public_file_bytes.decode("ascii").splitlines()[0])
        except (IndexError, UnicodeDecodeError, ValueError) as error:
            raise ValueError("bundled project public key is invalid") from error
        if bundled_public != pinned:
            raise ValueError("bundled project public key does not match its pinned key")
        if format_public_key(public) != pinned:
            raise ValueError("seal signature key does not match the pinned project key")
        if not ed25519_verify(public, manifest_bytes, signed):
            raise ValueError("bad seal signature")
        file_names: list[str] = []
        for item in files:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not isinstance(item.get("sha256"), str)
            ):
                raise ValueError("seal manifest file inventory is invalid")
            relative = item["path"]
            expected_hash = _digest_text(item["sha256"], f"file hash for {relative}")
            if not _safe_member(relative) or _private_key_like(relative):
                raise ValueError(f"seal contains private-key-like path: {relative}")
            member = f"project/{relative}"
            data = _read_member(archive, member, "project file")
            if _sha256(data) != expected_hash:
                raise ValueError(f"seal file hash mismatch: {relative}")
            file_names.append(member)
        if len(file_names) != len(set(file_names)):
            raise ValueError("seal manifest repeats a file")
        expected = {"seal/manifest.json", "seal/signature", *file_names}
        if set(names) != expected:
            raise ValueError("seal contains files not listed by its manifest")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in directories:
                if not isinstance(directory, str) or not _safe_member(directory) or _private_key_like(directory):
                    raise ValueError("seal manifest directory inventory is invalid")
                (root / directory).mkdir(parents=True, exist_ok=True)
            for member in file_names:
                target = root / member.removeprefix("project/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_read_member(archive, member, "project file"))
            if tree_digest(root) != manifest_tree_digest:
                raise ValueError("seal tree digest mismatch")
        expected_fingerprint = _fingerprint(expect_key) if expect_key is not None else None
        trusted_values = (trusted_keys,) if isinstance(trusted_keys, str) else trusted_keys
        trusted_fingerprints = {_fingerprint(key) for key in trusted_values}
        signer_fingerprint = key_fingerprint(pinned)
        if expected_fingerprint is not None and signer_fingerprint != expected_fingerprint:
            raise ValueError(f"expected signer fingerprint {expected_fingerprint}, got {signer_fingerprint}")
        authenticated = expected_fingerprint is not None or signer_fingerprint in trusted_fingerprints
    public_key = pinned
    return {
        "valid": True,
        "public_key": public_key,
        "fingerprint": key_fingerprint(public_key),
        "tree_digest": manifest["tree_digest"],
        "file_count": len(file_names),
        "authenticated": authenticated,
        "status": "authenticated" if authenticated else "self-consistent but UNAUTHENTICATED (trust-on-first-use)",
    }
