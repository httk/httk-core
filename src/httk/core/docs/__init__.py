#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Shared versioned httk documentation machinery.

The package composes immutable release trees alongside replaceable ``dev:main``
trees, writes root/page manifests and redirects, validates locks and
inventories, and supplies the Furo-aligned version selector used by published
sites.
"""

from .config import (
    ConfigError,
    InternalDependency,
    VersioningConfig,
    load_versioning_config,
)
from .inventories import InventoryError, fetch_inventory, read_inventory_header
from .lockfile import (
    LockError,
    check_lock,
    compute_input_hash,
    filter_lock_pins,
    generate_lock,
    internal_pins,
    read_lock_pins,
)
from .manifests import (
    build_page_manifest,
    build_version_manifest,
    read_version_manifest,
    write_page_manifest,
    write_version_manifest,
)
from .redirect import root_redirect_html, write_root_redirect
from .release import ReleaseCheck, ReleaseError, check_release, dependency_doc_targets
from .semver import (
    Version,
    VersionError,
    highest_version,
    is_release_dir_name,
    parse_tag,
    parse_version,
)
from .sitetree import ComposeError, ComposeResult, ImmutabilityError, compose_site

__all__ = [
    "ComposeResult",
    "ComposeError",
    "ConfigError",
    "ImmutabilityError",
    "InternalDependency",
    "InventoryError",
    "LockError",
    "ReleaseCheck",
    "ReleaseError",
    "Version",
    "VersionError",
    "VersioningConfig",
    "build_page_manifest",
    "build_version_manifest",
    "check_lock",
    "check_release",
    "compose_site",
    "compute_input_hash",
    "dependency_doc_targets",
    "fetch_inventory",
    "filter_lock_pins",
    "generate_lock",
    "highest_version",
    "internal_pins",
    "is_release_dir_name",
    "load_versioning_config",
    "parse_tag",
    "parse_version",
    "read_inventory_header",
    "read_lock_pins",
    "read_version_manifest",
    "root_redirect_html",
    "write_page_manifest",
    "write_root_redirect",
    "write_version_manifest",
]
