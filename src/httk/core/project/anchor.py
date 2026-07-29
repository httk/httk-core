"""The httk project anchor: the ``.httk-project`` directory and its metadata.

A *project* is to a campaign what a Git repository is to a source tree: a
directory marked, at its root, by a small control directory that every command
discovers by walking upward from wherever it is run. Here that directory is
``.httk-project`` and its manifest is ``project.json``.

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
from httk.core.ed25519 import ed25519_generate_seed, ed25519_public_key

from ._util import write_json_atomic

#: The control directory that marks a project root, like ``.git`` marks a
#: repository. Every command discovers a project by finding this directory at or
#: above the working directory.
PROJECT_DIRECTORY = ".httk-project"
#: The versioned metadata document inside :data:`PROJECT_DIRECTORY`.
PROJECT_FILE = "project.json"
#: How a public key is written wherever project metadata records one.
PUBLIC_KEY_PREFIX = "ed25519:"


def discover_project(start: str | os.PathLike[str] | None = None) -> Path | None:
    """Find the nearest project root at or above *start*."""

    path = Path.cwd() if start is None else Path(start)
    path = path.expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / PROJECT_DIRECTORY / PROJECT_FILE).is_file():
            return candidate
    return None


def require_project(start: str | os.PathLike[str] | None = None) -> Path:
    """Return the nearest project root, refusing when there is none."""

    project = discover_project(start)
    if project is None:
        raise ValueError("no .httk-project project exists at or above the working directory")
    return project


def read_project(root: str | os.PathLike[str]) -> dict[str, object]:
    """Read and validate the ``project.json`` of the project rooted at *root*."""

    path = Path(root).resolve() / PROJECT_DIRECTORY / PROJECT_FILE
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"project metadata is not a JSON object: {path}")
    if value.get("format") != "httk-project" or value.get("format_version") != 1:
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
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"project member {name!r} must be a mapping")
    metadata = read_project(root)
    metadata[name] = dict(value)
    write_json_atomic(Path(root).expanduser().resolve() / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata


def format_public_key(raw: bytes) -> str:
    """Return the recorded representation of one raw Ed25519 public key."""

    if len(raw) != 32:
        raise ValueError("an Ed25519 public key is 32 bytes")
    return PUBLIC_KEY_PREFIX + base64.b64encode(raw).decode("ascii")


def parse_public_key(value: str) -> bytes:
    """Decode a recorded public key, accepting the bare base64 spelling too."""

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
    """Normalize any accepted public key spelling to the recorded one."""

    return format_public_key(parse_public_key(value))


def key_fingerprint(value: str) -> str:
    """Return the stable display fingerprint of one public key."""

    return "sha256:" + hashlib.sha256(parse_public_key(value)).hexdigest()


def _write_project_key(control: Path) -> str:
    seed = ed25519_generate_seed()
    key_dir = control / "keys"
    key_dir.mkdir()
    private_path = key_dir / "project.seed"
    descriptor = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(base64.b64encode(seed).decode("ascii") + "\n")
    os.chmod(private_path, 0o600)
    public = ed25519_public_key(seed)
    (key_dir / "project.pub").write_text(
        base64.b64encode(public).decode("ascii") + "\n",
        encoding="ascii",
    )
    return format_public_key(public)


def project_public_key_path(root: str | os.PathLike[str]) -> Path:
    """Return where a project keeps its own signing key's public half."""

    return Path(root).expanduser().resolve() / PROJECT_DIRECTORY / "keys" / "project.pub"


def read_public_key_file(path: str | os.PathLike[str]) -> str:
    """Read one ``*.pub`` file and return its recorded public key."""

    try:
        text = Path(path).expanduser().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read public key file: {path}") from exc
    if not text:
        raise ValueError(f"public key file is empty: {path}")
    return canonical_public_key(text.splitlines()[0])


def pinned_project_key(metadata: Mapping[str, object]) -> str | None:
    """Return the project's own pinned public key, or ``None`` when absent."""

    value = metadata.get("public_key")
    return canonical_public_key(value) if isinstance(value, str) and value else None


def trusted_project_keys(metadata: Mapping[str, object]) -> tuple[str, ...]:
    """Return every key *metadata* pins: the project's own and any adopted one.

    The pinned key of ``project.json`` is the trust anchor a manifest is checked
    against. ``trusted_keys`` carries the additional anchors an operator has
    adopted deliberately — most often the legacy identities an imported *httk*
    v1 project signed its old manifests with.
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
    """

    project = require_project(root)
    metadata = read_project(project)
    metadata["public_key"] = read_public_key_file(project_public_key_path(project))
    write_json_atomic(project / PROJECT_DIRECTORY / PROJECT_FILE, metadata)
    return metadata


def trust_project_key(root: str | os.PathLike[str] | None, key: str) -> dict[str, object]:
    """Adopt one further public key as a trust anchor of this project."""

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
    default_queue: str | None = None,
    manifest_exclusions: Iterable[str] = (),
) -> dict[str, object]:
    """Initialize the project anchor: its metadata, its key, and its remotes dir.

    This creates only the anchor — ``.httk-project`` with ``project.json``, the
    project's Ed25519 signing key, and the ``remotes`` directory. It creates no
    workflow workspace; a workflow installation layers that on top of the anchor
    so that a core-only installation still has a working project.
    """

    project = Path(root).expanduser().resolve()
    project.mkdir(parents=True, exist_ok=True)
    control = project / PROJECT_DIRECTORY
    control.mkdir(exist_ok=False)
    metadata: dict[str, object] = {
        "format": "httk-project",
        "format_version": 1,
        "project_id": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "default_queue": default_queue,
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
    """

    project = Path(root).expanduser().resolve()
    legacy = Path(source).expanduser().resolve() if source is not None else project / "ht.project"
    if not legacy.is_dir():
        raise FileNotFoundError(legacy)
    parser = configparser.ConfigParser()
    parser.read(legacy / "config", encoding="utf-8")
    project_name = name if name is not None else str(parser.get("main", "project_name", fallback=project.name))
    metadata = initialize_project(project, name=project_name)
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
