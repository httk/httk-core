"""Read installed httk plugins."""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ..userdirs import data_home
from .manifest import PLUGIN_MANIFEST, PluginManifest, PluginProgram, parse_plugin_manifest

PLUGIN_METADATA = "plugin.json"
_LOGGER = logging.getLogger(__name__)

__all__ = [
    "PLUGIN_MANIFEST",
    "PLUGIN_METADATA",
    "InstalledPlugin",
    "PluginManifest",
    "PluginProgram",
    "build_plugin",
    "install_plugin",
    "installed_plugins",
    "parse_plugin_manifest",
    "plugin_program",
    "plugin_root",
    "plugins_home",
    "shims_home",
    "uninstall_plugin",
]


@dataclass(frozen=True)
class InstalledPlugin:
    """Describe one installed plugin and its installer metadata.

    :param name: Name the installed plugin directory.
    :param root: Locate the installed plugin directory.
    :param manifest: Provide the parsed plugin.json object.
    :param metadata: Provide the parsed plugin.json object.
    """

    name: str
    root: Path
    manifest: PluginManifest
    metadata: Mapping[str, object]


def plugins_home() -> Path:
    """Return the installed plugin directory.

    :return: The plugin data directory.
    """

    return data_home() / "plugins"


def shims_home() -> Path:
    """Return the plugin shim directory.

    :return: The shim data directory.
    """

    return data_home() / "bin"


def _read_metadata(root: Path) -> Mapping[str, object]:
    path = root / PLUGIN_METADATA
    try:
        with path.open(encoding="utf-8") as handle:
            metadata = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {PLUGIN_METADATA}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"{PLUGIN_METADATA} must contain a JSON object")
    return cast(Mapping[str, object], metadata)


def _read_installed(root: Path) -> InstalledPlugin:
    return InstalledPlugin(root.name, root, parse_plugin_manifest(root), _read_metadata(root))


def installed_plugins() -> tuple[InstalledPlugin, ...]:
    """Read all valid installed plugins.

    :return: Valid installed plugins in directory-name order.
    """

    home = plugins_home()
    if not home.is_dir():
        return ()
    result: list[InstalledPlugin] = []
    for root in sorted(home.iterdir(), key=lambda path: path.name):
        if root.name.startswith(".") or not root.is_dir():
            continue
        try:
            result.append(_read_installed(root))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _LOGGER.warning("Skipping malformed installed plugin %s: %s", root, exc)
    return tuple(result)


def plugin_root(name: str) -> Path:
    """Return the root of an installed plugin.

    :param name: Name the installed plugin directory.
    :return: The installed plugin directory.
    :raises ValueError: If the plugin is not installed.
    """

    root = plugins_home() / name
    if root.parent != plugins_home() or not root.is_dir() or not (root / PLUGIN_METADATA).is_file():
        raise ValueError(f"plugin {name!r} is not installed")
    return root


def plugin_program(name: str, program: str) -> Path:
    """Return the absolute path of an installed plugin program.

    :param name: Name the installed plugin.
    :param program: Name the declared program.
    :return: The program's absolute path.
    :raises ValueError: If the plugin or program is unavailable.
    """

    installed = _read_installed(plugin_root(name))
    declared = next((entry for entry in installed.manifest.programs if entry.name == program), None)
    if declared is None:
        raise ValueError(f"plugin {name!r} does not declare program {program!r}")
    path = installed.root / declared.file
    if installed.metadata.get("built") is False or not path.is_file() or path.is_symlink():
        raise ValueError(f"plugin {name!r} program {program!r} is not built; run: httk plugin build {name}")
    return path.resolve()


from .install import build_plugin, install_plugin, uninstall_plugin
