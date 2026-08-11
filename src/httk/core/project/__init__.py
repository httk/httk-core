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
from .seal import PROJECT_PRIVATE_KEY_RELATIVE_PATH, seal_project, verify_seal

__all__ = [
    "PROJECT_DIRECTORY",
    "PROJECT_FILE",
    "PROJECT_PRIVATE_KEY_RELATIVE_PATH",
    "PUBLIC_KEY_PREFIX",
    "LegacyProjectError",
    "canonical_public_key",
    "discover_project",
    "format_public_key",
    "import_v1_project",
    "initialize_project",
    "key_fingerprint",
    "parse_public_key",
    "pin_project_key",
    "pinned_project_key",
    "project_public_key_path",
    "read_project",
    "read_project_section",
    "read_public_key_file",
    "require_project",
    "seal_project",
    "trust_project_key",
    "trusted_project_keys",
    "verify_seal",
    "write_project_section",
]
