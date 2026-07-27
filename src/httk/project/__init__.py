"""The httk project anchor and the umbrella ``httk project`` command.

A *project* is a directory marked at its root by a ``.httk-project`` control
directory, discovered by walking upward exactly as ``git`` finds a ``.git``.
This package owns that anchor — creating it, reading and validating its
``project.json``, and managing its Ed25519 identity and trust anchors — and the
extensible :command:`httk project` command that operates on it. It creates no
workflow workspace; that is layered on by a workflow installation.

The anchor API is re-exported here for convenience; the command and its
extension registry live in :mod:`httk.project.cli`.
"""

from .anchor import (
    PROJECT_DIRECTORY,
    PROJECT_FILE,
    PUBLIC_KEY_PREFIX,
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

__all__ = [
    "PROJECT_DIRECTORY",
    "PROJECT_FILE",
    "PUBLIC_KEY_PREFIX",
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
    "trust_project_key",
    "trusted_project_keys",
    "write_project_section",
]
