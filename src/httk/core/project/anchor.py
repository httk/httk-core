"""The httk project anchor: the ``httk_project`` directory and its metadata.

A *project* is to a campaign what a Git repository is to a source tree: a
directory marked, at its root, by a small control directory that every command
discovers by walking upward from wherever it is run. Here that directory is
``httk_project`` and its manifest is ``project.json``.

This module owns the anchor and nothing above it. It creates the control
directory, reads and validates ``project.json``, walks upward to discover the
nearest project, and manages the project's Ed25519 identity key and the trust
anchors a signed manifest is later checked against. It creates no workflow
workspace: that is an add-on a workflow installation layers on top of the
anchor, so the anchor stays useful to a core-only installation.

The on-disk format — the ``format`` and ``format_version`` members, the key
file names and modes, and the directory layout — is shared with *httk-workflow*
so its manifests and doctor interoperate with core projects.
"""

import base64
import configparser
import hashlib
import json
import os
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path

# Imported from the submodule rather than the ``httk.core`` package so this
# module stays importable while ``httk.core`` itself is still initializing: a
# workflow installation imports the project CLI during core's plugin discovery.
from httk.core.crypto import ed25519_generate_seed, ed25519_public_key

from .._json import write_json_atomic

#: The control directory that marks a project root, like ``.git`` marks a
#: repository. Every command discovers a project by finding this directory at or
#: above the working directory.
PROJECT_DIRECTORY = "httk_project"
#: The versioned metadata document inside :data:`PROJECT_DIRECTORY`.
PROJECT_FILE = "project.json"
#: How a public key is written wherever project metadata records one.
PUBLIC_KEY_PREFIX = "ed25519:"


class LegacyProjectError(ValueError):
    """Raised when discovery finds an httk v1 ``ht.project`` directory.

    Carries the offending directory as :attr:`root` so a caller that
    deliberately handles it (for example read-only verification of a v1
    manifest) does not have to parse the message.

    :param message: Diagnostic explaining the legacy project and its remedy.
    :param root: Directory containing the legacy project marker.
    """

    def __init__(self, message: str, *, root: Path) -> None:
        super().__init__(message)
        self.root = root


def _legacy_project_error(candidate: Path) -> LegacyProjectError | None:
    if (candidate / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
        return None
    if (candidate / "ht.project").is_dir():
        return LegacyProjectError(
            f"found an httk v1 project ('ht.project') at {candidate}; "
            f"create the httk v2 anchor with: httk project import-v1 {candidate}",
            root=candidate,
        )
    return None


def discover_project(start: str | os.PathLike[str] | None = None) -> Path | None:
    """Find the nearest project root, or refuse a legacy one, at or above *start*.

    Discovery walks from start and its parents, treating a file start as its
    containing directory. If it finds a legacy ht.project marker, the exception
    identifies the required remedy: run httk project import-v1 PATH.

    :param start: Directory or file from which to begin the upward search, or None for the current directory.
    :return: Nearest project root, or None when no marker is found.
    :raises httk.core.project.LegacyProjectError: If discovery finds a v1 project marker.
    """

    path = Path.cwd() if start is None else Path(start)
    path = path.expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
            return candidate
        error = _legacy_project_error(candidate)
        if error is not None:
            raise error
    return None


def require_project(start: str | os.PathLike[str] | None = None) -> Path:
    """Return the nearest project root, refusing when there is none.

    :param start: Directory or file from which to begin the upward search, or None for the current directory.
    :return: Nearest project root.
    :raises httk.core.project.LegacyProjectError: If discovery finds a v1 project marker.
    :raises ValueError: If no project marker is found.
    """

    project = discover_project(start)
    if project is None:
        raise ValueError("no httk project exists at or above the working directory")
    return project


def read_project(root: str | os.PathLike[str]) -> dict[str, object]:
    """Read and validate the ``project.json`` of the project rooted at *root*.

    :param root: Project root whose manifest is read.
    :return: Validated project metadata.
    :raises ValueError: If the manifest is not an httk project manifest.
    """

    path = Path(root).resolve() / PROJECT_DIRECTORY / PROJECT_FILE
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"project metadata is not a JSON object: {path}")
    if value.get("format") != "httk-project" or value.get("format_version") != 2:
        raise ValueError("unsupported httk project format")
    return value


def read_project_section(root: str | os.PathLike[str], name: str) -> dict[str, object]:
    """Return one named object member of ``project.json``, empty when absent.

    A *section* is a top-level member of the project manifest that some layer
    above the anchor owns — the workflow workspace registry, a campaign map —
    and reads and writes as a whole. The anchor does not interpret the member;
    it only guarantees that what a caller stores under a name comes back as the
    object it was, and refuses a member that some other writer has left as a
    non-object so a caller never silently reads a scalar as a mapping.

    :param root: Project root whose manifest is read.
    :param name: Top-level manifest member to retrieve.
    :return: A copy of the named object, or an empty object when absent.
    :raises ValueError: If the named manifest member is not an object.
    """

    value = read_project(root).get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"project member {name!r} is not a JSON object")
    return dict(value)


def write_project_section(
    root: str | os.PathLike[str],
    name: str,
    value: Mapping[str, object],
) -> dict[str, object]:
    """Store one named object member of ``project.json`` and return the metadata.

    The write is an ordinary read-modify-write of the validated manifest, so the
    members the anchor owns are preserved untouched and only the named section is
    replaced. The section must be a mapping; the anchor stores its members
    verbatim without interpreting them.

    :param root: Project root whose manifest is updated.
    :param name: Top-level manifest member to replace.
    :param value: Object members to store under the name.
    :return: Updated project metadata.
    :raises ValueError: If the named section is not a mapping.
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"project member {name!r} must be a mapping")
    metadata = read_project(root)
    metadata[name] = dict(value)
    write_json_atomic(Path(root).expanduser().resolve() / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata


def format_public_key(raw: bytes) -> str:
    """Return the recorded representation of one raw Ed25519 public key.

    :param raw: Raw public-key bytes to record.
    :return: Canonical prefixed public-key text.
    :raises ValueError: If the key is not 32 bytes long.
    """

    if len(raw) != 32:
        raise ValueError("an Ed25519 public key is 32 bytes")
    return PUBLIC_KEY_PREFIX + base64.b64encode(raw).decode("ascii")


def parse_public_key(value: str) -> bytes:
    """Decode a recorded public key, accepting the bare base64 spelling too.

    :param value: Public-key text to decode.
    :return: Raw public-key bytes.
    :raises ValueError: If the algorithm, encoding, or key length is invalid.
    """

    text = value.strip()
    if text.startswith(PUBLIC_KEY_PREFIX):
        text = text[len(PUBLIC_KEY_PREFIX) :]
    elif ":" in text:
        raise ValueError(f"unsupported public key algorithm: {value!r}")
    try:
        raw = base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError(f"public key is not valid base64: {value!r}") from exc
    if len(raw) != 32:
        raise ValueError(f"public key is not a 32-byte Ed25519 key: {value!r}")
    return raw


def canonical_public_key(value: str) -> str:
    """Normalize any accepted public key spelling to the recorded one.

    :param value: Accepted public-key text to normalize.
    :return: Canonical prefixed public-key text.
    :raises ValueError: If the public-key text is invalid.
    """

    return format_public_key(parse_public_key(value))


def key_fingerprint(value: str) -> str:
    """Return the stable display fingerprint of one public key.

    :param value: Public-key text whose fingerprint is calculated.
    :return: Stable SHA-256 fingerprint text.
    :raises ValueError: If the public-key text is invalid.
    """

    return "sha256:" + hashlib.sha256(parse_public_key(value)).hexdigest()


def _write_project_key(control: Path) -> str:
    # Imported lazily to keep ``httk.core.identity`` importable while this
    # package is still initializing during core's plugin discovery.
    from ..identity import _write_key_file_atomic

    seed = ed25519_generate_seed()
    key_dir = control / "keys"
    key_dir.mkdir()
    _write_key_file_atomic(
        key_dir / "project.seed",
        base64.b64encode(seed).decode("ascii") + "\n",
        0o600,
        exclusive=True,
    )
    public = ed25519_public_key(seed)
    _write_key_file_atomic(key_dir / "project.pub", base64.b64encode(public).decode("ascii") + "\n", 0o644)
    return format_public_key(public)


def project_public_key_path(root: str | os.PathLike[str]) -> Path:
    """Return where a project keeps its own signing key's public half.

    :param root: Project root containing the anchor.
    :return: Path to the project's public key file.
    """

    return Path(root).expanduser().resolve() / PROJECT_DIRECTORY / "keys" / "project.pub"


def read_public_key_file(path: str | os.PathLike[str]) -> str:
    """Read one public-key file and return its recorded public key.

    :param path: Public-key file to read.
    :return: Canonical public-key text from the first line.
    :raises ValueError: If the file cannot be read, is empty, or contains an invalid key.
    """

    try:
        text = Path(path).expanduser().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read public key file: {path}") from exc
    if not text:
        raise ValueError(f"public key file is empty: {path}")
    return canonical_public_key(text.splitlines()[0])


def pinned_project_key(metadata: Mapping[str, object]) -> str | None:
    """Return the project's own pinned public key, or None when absent.

    :param metadata: Project metadata containing the optional public-key member.
    :return: Canonical pinned key, or None when the metadata has no key.
    :raises ValueError: If the pinned key is present but invalid.
    """

    value = metadata.get("public_key")
    return canonical_public_key(value) if isinstance(value, str) and value else None


def trusted_project_keys(metadata: Mapping[str, object]) -> tuple[str, ...]:
    """Return every key *metadata* pins: the project's own and any adopted one.

    The pinned key of ``project.json`` is the trust anchor a manifest is checked
    against. ``trusted_keys`` carries the additional anchors an operator has
    adopted deliberately — most often the legacy identities an imported *httk*
    v1 project signed its old manifests with.

    :param metadata: Project metadata whose trust anchors are read.
    :return: Unique canonical project and adopted trust anchors.
    :raises ValueError: If trusted_keys is not a string array or contains an invalid key.
    """

    keys: list[str] = []
    own = pinned_project_key(metadata)
    if own is not None:
        keys.append(own)
    extra = metadata.get("trusted_keys", [])
    if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
        raise ValueError("trusted_keys must be an array of strings")
    for item in extra:
        canonical = canonical_public_key(str(item))
        if canonical not in keys:
            keys.append(canonical)
    return tuple(keys)


def pin_project_key(root: str | os.PathLike[str] | None = None) -> dict[str, object]:
    """Adopt the project's current ``keys/project.pub`` as its trust anchor.

    Pinning is always an explicit act. Verification trusts the key recorded in
    ``project.json`` and never the key a manifest carries in its own header, so
    adopting the key that is in the tree right now is exactly the decision an
    operator has to make consciously for an older project that has no pin.

    :param root: Project root, or None to discover the nearest project.
    :return: Updated project metadata.
    :raises ValueError: If no project exists or its public key is invalid.
    """

    project = require_project(root)
    metadata = read_project(project)
    metadata["public_key"] = read_public_key_file(project_public_key_path(project))
    write_json_atomic(project / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata


def trust_project_key(root: str | os.PathLike[str] | None, key: str) -> dict[str, object]:
    """Adopt one further public key as a trust anchor of this project.

    :param root: Project root, or None to discover the nearest project.
    :param key: Public key to add to the project's trusted anchors.
    :return: Updated project metadata.
    :raises ValueError: If no project exists, the key is invalid, or trusted_keys is invalid.
    """

    project = require_project(root)
    metadata = read_project(project)
    canonical = canonical_public_key(key)
    existing = metadata.get("trusted_keys", [])
    if not isinstance(existing, list):
        raise ValueError("trusted_keys must be an array of strings")
    keys = [str(item) for item in existing]
    if canonical not in trusted_project_keys(metadata):
        keys.append(canonical)
    metadata["trusted_keys"] = keys
    write_json_atomic(project / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata


def initialize_project(
    root: str | os.PathLike[str],
    *,
    name: str,
    description: str = "",
    manifest_exclusions: Iterable[str] = (),
) -> dict[str, object]:
    """Initialize the project anchor: its metadata, its key, and its remotes dir.

    This creates only the anchor — ``httk_project`` with ``project.json``, the
    project's Ed25519 signing key, and the ``remotes`` directory. It creates no
    workflow workspace; a workflow installation layers that on top of the anchor
    so that a core-only installation still has a working project.

    :param root: Directory in which to create the project anchor.
    :param name: Human-readable project name.
    :param description: Optional project description.
    :param manifest_exclusions: Relative paths excluded from project manifests.
    :return: Newly written project metadata.
    :raises httk.core.project.LegacyProjectError: If root contains a v1 project marker.
    """

    project = Path(root).expanduser().resolve()
    error = _legacy_project_error(project)
    if error is not None:
        raise error
    return _initialize_project_unchecked(
        project,
        name=name,
        description=description,
        manifest_exclusions=manifest_exclusions,
    )


def _initialize_project_unchecked(
    project: Path,
    *,
    name: str,
    description: str = "",
    manifest_exclusions: Iterable[str] = (),
) -> dict[str, object]:
    project.mkdir(parents=True, exist_ok=True)
    control = project / PROJECT_DIRECTORY
    control.mkdir(exist_ok=False)
    metadata: dict[str, object] = {
        "format": "httk-project",
        "format_version": 2,
        "project_id": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "manifest_exclusions": list(manifest_exclusions),
    }
    write_json_atomic(control / PROJECT_FILE, metadata)
    # The public half of the signing key is pinned in project.json at creation,
    # so manifest verification has a trust anchor that is not simply whatever
    # key the manifest being verified happens to name in its own header.
    metadata["public_key"] = _write_project_key(control)
    metadata["trusted_keys"] = []
    write_json_atomic(control / PROJECT_FILE, metadata)
    (control / "remotes").mkdir()
    return metadata


def import_v1_project(
    root: str | os.PathLike[str],
    *,
    source: str | os.PathLike[str] | None = None,
    name: str | None = None,
) -> dict[str, object]:
    """Create the project anchor from a legacy ``ht.project`` directory.

    Only the anchor is created: the project's metadata and the adoption of the
    legacy identities its old manifests were signed with. A workflow
    installation adds the workspace and any queue import on top of this.

    :param root: Directory in which to create the new project anchor.
    :param source: Legacy project directory, or root/ht.project when omitted.
    :param name: Optional replacement project name.
    :return: Imported project metadata.
    :raises FileNotFoundError: If the legacy project directory does not exist.
    """

    project = Path(root).expanduser().resolve()
    legacy = Path(source).expanduser().resolve() if source is not None else project / "ht.project"
    if not legacy.is_dir():
        raise FileNotFoundError(legacy)
    parser = configparser.ConfigParser()
    parser.read(legacy / "config", encoding="utf-8")
    project_name = name if name is not None else str(parser.get("main", "project_name", fallback=project.name))
    # Importing v1 intentionally creates the v2 anchor beside its ht.project
    # directory through the private unchecked initializer, so no legacy refusal
    # applies here.
    metadata = _initialize_project_unchecked(project, name=project_name)
    metadata["imported_from"] = str(legacy)
    public_keys: list[str] = []
    trusted: list[str] = []
    destination = project / PROJECT_DIRECTORY / "keys" / "legacy-public"
    for public in sorted((legacy / "keys").glob("*.pub")) if (legacy / "keys").is_dir() else ():
        destination.mkdir(exist_ok=True)
        target = destination / public.name
        target.write_bytes(public.read_bytes())
        public_keys.append(str(target.relative_to(project)))
        try:
            recorded = read_public_key_file(target)
        except ValueError:
            # A legacy key file this implementation cannot read is still copied
            # for the record, but it cannot become a trust anchor.
            continue
        if recorded not in trusted:
            trusted.append(recorded)
    metadata["legacy_public_keys"] = public_keys
    # The imported identities verify the legacy manifests this project was
    # signed with before it was imported, so they are pinned like the project's
    # own key rather than only copied into the tree.
    metadata["trusted_keys"] = trusted
    metadata["legacy_queue_imported"] = False
    write_json_atomic(project / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata
