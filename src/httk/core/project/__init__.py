"""The httk project anchor and the core-owned ``httk project`` command.

A *project* is a directory marked at its root by a ``httk_project`` control
directory, discovered by walking upward exactly as ``git`` finds a ``.git``.
This package owns that anchor — creating it, reading and validating its
``project.json``, and managing its Ed25519 identity and trust anchors — and the
core-only :command:`httk project` command that operates on it. It creates no
workflow workspace; that is layered on by a workflow installation.

The anchor API is re-exported here for convenience; the command and its
implementation live in :mod:`httk.core.project.cli`.
"""

from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    PUBLIC_KEY_PREFIX,
    LegacyProjectError,
    canonical_public_key,
    discover_project,
    format_public_key,
    import_v1_project,
    initialize_project,
    key_fingerprint,
    parse_public_key,
    pin_project_key,
    pinned_project_key,
    project_public_key_path,
    read_project,
    read_project_section,
    read_public_key_file,
    require_project,
    trust_project_key,
    trusted_project_keys,
    write_project_section,
)
from .export import PROJECT_PRIVATE_KEY_RELATIVE_PATH, export_project, verify_export
from .manifests import (
    DEFAULT_MANIFEST_EXCLUSIONS,
    ManifestVerification,
    create_manifest,
    project_exclusions,
    resolve_trusted_keys,
    verify_manifest,
)
from .members import (
    ProjectMember,
    ProjectMemberHandler,
    members_path,
    project_members,
    register_project_member,
    unregister_project_member,
    update_project_member_path,
)
from .sealing import (
    Discrepancy,
    Seal,
    SealedError,
    SealError,
    SealKeys,
    SealReport,
    SealVerification,
    default_project_keys,
    is_project_sealed,
    project_seal_path,
    read_seal,
    resolve_seal_keys,
    seal_project,
    unseal_project,
    verify_project,
    verify_seal,
)

__all__ = [
    "DEFAULT_MANIFEST_EXCLUSIONS",
    "PROJECT_DIRECTORY",
    "PROJECT_FILE",
    "PROJECT_PRIVATE_KEY_RELATIVE_PATH",
    "PUBLIC_KEY_PREFIX",
    "Discrepancy",
    "LegacyProjectError",
    "ManifestVerification",
    "ProjectMember",
    "ProjectMemberHandler",
    "Seal",
    "SealError",
    "SealKeys",
    "SealReport",
    "SealVerification",
    "SealedError",
    "canonical_public_key",
    "create_manifest",
    "default_project_keys",
    "discover_project",
    "export_project",
    "format_public_key",
    "import_v1_project",
    "initialize_project",
    "is_project_sealed",
    "key_fingerprint",
    "members_path",
    "parse_public_key",
    "pin_project_key",
    "pinned_project_key",
    "project_exclusions",
    "project_members",
    "project_public_key_path",
    "project_seal_path",
    "read_project",
    "read_project_section",
    "read_public_key_file",
    "read_seal",
    "register_project_member",
    "require_project",
    "resolve_seal_keys",
    "resolve_trusted_keys",
    "seal_project",
    "trust_project_key",
    "trusted_project_keys",
    "unregister_project_member",
    "unseal_project",
    "update_project_member_path",
    "verify_export",
    "verify_manifest",
    "verify_project",
    "verify_seal",
    "write_project_section",
]
