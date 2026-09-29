"""Simulation-code support registry."""

#
#    The high-throughput toolkit (httk)
#    Copyright (C) 2012-2024 the httk AUTHORS
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation; either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
import importlib
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import ModuleType

__all__ = ["CodeSupport", "code_support", "known_codes", "register_code"]


@dataclass(frozen=True)
class CodeSupport:
    """Store registration metadata for one simulation-code support package.

    :param name: The code name; also the ``<name>-`` bridge command prefix and
        the environment-variable stem.
    :param bridge: The dotted bridge module path. The module defines
        ``add_commands(subparsers)`` and ``run_command(namespace) -> int``.
    :param bash_api: The ``"package:filename"`` resource of the Bash API
        script, or ``None``.
    """

    name: str
    bridge: str
    bash_api: str | None

    def resolve_bridge(self) -> ModuleType:
        """Import and return the bridge module.

        :return: The imported bridge module.
        """

        return importlib.import_module(self.bridge)

    def bash_api_path(self) -> Path | None:
        """Return the filesystem path of the Bash API script.

        :return: The script path, or ``None`` if no Bash API is registered.
        :raises FileNotFoundError: If the registered resource does not exist.
        """

        if self.bash_api is None:
            return None
        package, _, filename = self.bash_api.partition(":")
        resource = files(package).joinpath(filename)
        if not resource.is_file():
            raise FileNotFoundError(f"code {self.name!r} Bash API resource not found: {self.bash_api!r}")
        # ponytail: assumes a filesystem install; zipped packages would need importlib.resources.as_file.
        return Path(str(resource))


_CODE_NAME = re.compile(r"[a-z][a-z0-9_]*")
_DOTTED = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_BRIDGE = re.compile(_DOTTED)
_BASH_API = re.compile(_DOTTED + r":[A-Za-z0-9_][A-Za-z0-9_.-]*")
_codes: dict[str, CodeSupport] = {}


def register_code(name: str, *, bridge: str, bash_api: str | None = None) -> None:
    """Register a simulation-code support package.

    Registration stores strings only; nothing is imported or resolved until
    :meth:`CodeSupport.resolve_bridge` or :meth:`CodeSupport.bash_api_path` is
    called. Re-registering a name with identical values is a no-op.

    :param name: The code name, matching ``[a-z][a-z0-9_]*``.
    :param bridge: The dotted bridge module path, e.g. ``"httk.codes.vasp._bridge"``.
    :param bash_api: The ``"package:filename"`` Bash API resource, e.g.
        ``"httk.codes.vasp:httk-vasp.sh"``, or ``None``.
    :raises ValueError: If a value is invalid or ``name`` is registered with different values.
    """

    if not isinstance(name, str) or _CODE_NAME.fullmatch(name) is None:
        raise ValueError(f"invalid code name: {name!r}")
    if not isinstance(bridge, str) or _BRIDGE.fullmatch(bridge) is None:
        raise ValueError(f"code bridge must be a dotted module path: {bridge!r}")
    if bash_api is not None and (not isinstance(bash_api, str) or _BASH_API.fullmatch(bash_api) is None):
        raise ValueError(f"code Bash API must be a 'package:filename' resource: {bash_api!r}")
    support = CodeSupport(name=name, bridge=bridge, bash_api=bash_api)
    existing = _codes.setdefault(name, support)
    if existing != support:
        raise ValueError(f"code is already registered with different values: {name!r}")


def code_support(name: str) -> CodeSupport:
    """Return code-support metadata without importing its implementation.

    :param name: The code name to look up.
    :return: The registered code-support metadata.
    :raises KeyError: If ``name`` is not registered.
    """

    try:
        return _codes[name]
    except KeyError:
        known = ", ".join(known_codes()) or "(none)"
        raise KeyError(f"no code support registered for {name!r}; known: {known}") from None


def known_codes() -> tuple[str, ...]:
    """Return registered code names without resolving anything.

    :return: Registered code names in sorted order.
    """

    return tuple(sorted(_codes))
