"""Provide per-user httk configuration and data directories.

Use XDG configuration and data conventions by default: configuration lives
under ``~/.config/httk`` and data under ``~/.local/share/httk``. The
``HTTK_CONFIG_HOME`` and ``HTTK_DATA_HOME`` environment variables override
those directories.
"""

import os
from pathlib import Path

__all__ = ["config_home", "data_home"]


def config_home() -> Path:
    """Return the httk configuration directory.

    :return: Resolved per-user configuration directory.
    """

    override = os.environ.get("HTTK_CONFIG_HOME")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return (base / "httk").resolve()


def data_home() -> Path:
    """Return the httk data directory.

    :return: Resolved per-user data directory.
    """

    override = os.environ.get("HTTK_DATA_HOME")
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return (base / "httk").resolve()
