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

"""Load the strict ``docs/versioning.toml`` site configuration.

The supported shape is::

    [site]
    slug = "httk-atomistic"
    repository-url = "https://github.com/httk/httk-atomistic"
    main-branch = "main"
    import-roots = ["httk/atomistic", "httk/handlers"]

    [[internal-dependency]]
    distribution = "httk-core"
    slug = "httk-core"
    repository-url = "https://github.com/httk/httk-core"
    main-branch = "main"
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ConfigError", "InternalDependency", "VersioningConfig", "load_versioning_config"]


class ConfigError(ValueError):
    """Raised when a versioning TOML file is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class InternalDependency:
    """Documentation-site metadata for one internal httk distribution."""

    distribution: str
    slug: str
    repository_url: str
    main_branch: str = "main"


@dataclass(frozen=True)
class VersioningConfig:
    """Configuration for one versioned documentation site."""

    slug: str
    repository_url: str
    main_branch: str = "main"
    import_roots: tuple[str, ...] = ()
    internal_dependencies: tuple[InternalDependency, ...] = ()


def _error(path: Path, key: str, message: str) -> ConfigError:
    return ConfigError(f"{path}: {key}: {message}")


def _string(value: object, path: Path, key: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise _error(path, key, "must be a non-empty string")
    return value


def _mapping(value: object, path: Path, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _error(path, key, "must be a table")
    return value


def load_versioning_config(path: str | Path) -> VersioningConfig:
    """Read and validate a versioning TOML file, rejecting unknown keys."""

    config_path = Path(path)
    try:
        with config_path.open("rb") as stream:
            raw = tomllib.load(stream)
    except OSError as exc:
        raise ConfigError(f"{config_path}: cannot read file: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid TOML: {exc}") from exc

    if set(raw) != {"site", "internal-dependency"} and set(raw) != {"site"}:
        unknown = sorted(set(raw) - {"site", "internal-dependency"})
        if unknown:
            raise _error(config_path, unknown[0], "unknown key")
    site = _mapping(raw.get("site"), config_path, "site")
    allowed_site = {"slug", "repository-url", "main-branch", "import-roots"}
    unknown_site = sorted(set(site) - allowed_site)
    if unknown_site:
        raise _error(config_path, f"site.{unknown_site[0]}", "unknown key")
    if "slug" not in site:
        raise _error(config_path, "site.slug", "is required")
    if "repository-url" not in site:
        raise _error(config_path, "site.repository-url", "is required")
    slug = _string(site["slug"], config_path, "site.slug", allow_empty=True)
    repository_url = _string(site["repository-url"], config_path, "site.repository-url")
    main_branch = _string(site.get("main-branch", "main"), config_path, "site.main-branch")
    roots_value = site.get("import-roots", [])
    if not isinstance(roots_value, list) or any(not isinstance(root, str) or not root for root in roots_value):
        raise _error(config_path, "site.import-roots", "must be an array of non-empty strings")

    dependencies: list[InternalDependency] = []
    dependency_value = raw.get("internal-dependency", [])
    if not isinstance(dependency_value, list):
        raise _error(config_path, "internal-dependency", "must be an array of tables")
    allowed_dependency = {"distribution", "slug", "repository-url", "main-branch"}
    for index, item in enumerate(dependency_value):
        key_prefix = f"internal-dependency[{index}]"
        dependency = _mapping(item, config_path, key_prefix)
        unknown_dependency = sorted(set(dependency) - allowed_dependency)
        if unknown_dependency:
            raise _error(config_path, f"{key_prefix}.{unknown_dependency[0]}", "unknown key")
        for required in ("distribution", "slug", "repository-url"):
            if required not in dependency:
                raise _error(config_path, f"{key_prefix}.{required}", "is required")
        dependencies.append(
            InternalDependency(
                distribution=_string(dependency["distribution"], config_path, f"{key_prefix}.distribution"),
                slug=_string(dependency["slug"], config_path, f"{key_prefix}.slug", allow_empty=True),
                repository_url=_string(dependency["repository-url"], config_path, f"{key_prefix}.repository-url"),
                main_branch=_string(dependency.get("main-branch", "main"), config_path, f"{key_prefix}.main-branch"),
            )
        )
    return VersioningConfig(slug, repository_url, main_branch, tuple(roots_value), tuple(dependencies))
