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

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable, Iterable, Mapping

CallableRef = str | Callable[..., Any]


def resolve_callable(ref: CallableRef) -> Callable[..., Any]:
    """
    Resolve a callable reference.

    Accepts:
      - a callable object
      - a string of form "module.submodule:callable_name"
    """
    if callable(ref):
        return ref
    if not isinstance(ref, str):
        raise TypeError(f"Expected callable or str reference, got {type(ref)!r}")

    module_name, _, attr = ref.partition(":")
    if not module_name or not attr:
        raise ValueError(f"Invalid reference {ref!r}; expected 'module:callable'.")

    obj = getattr(import_module(module_name), attr)
    if not callable(obj):
        raise TypeError(f"Resolved {ref!r} to non-callable object {obj!r}")
    return obj


@dataclass(frozen=True)
class PluginSpec:
    """
    A minimal plugin spec.

    - `key`: selection key (e.g., a file extension like ".cif", or a format name like "cif")
    - `handler`: callable or "module:callable" reference (lazy)
    """
    key: str
    handler: CallableRef
    name: str | None = None  # optional display name


class PluginRegistry:
    """
    Registry mapping keys -> plugin specs.

    Intended use:
      - loaders: key is file extension ".cif"
      - savers: key is file extension ".cif" or format name
      - show/visualization: key is format/backend name
    """

    def __init__(self) -> None:
        self._by_key: dict[str, PluginSpec] = {}

    def register(self, *, key: str, handler: CallableRef, name: str | None = None) -> None:
        k = key
        self._by_key[k] = PluginSpec(key=k, handler=handler, name=name)

    def keys(self) -> list[str]:
        return sorted(self._by_key.keys())

    def get(self, key: str) -> PluginSpec | None:
        return self._by_key.get(key)

    def require(self, key: str) -> PluginSpec:
        spec = self.get(key)
        if spec is None:
            known = ", ".join(self.keys()) or "(none)"
            raise ValueError(f"No plugin registered for {key!r}. Known: {known}")
        return spec

    def dispatch(self, key: str, *args: Any, **kwargs: Any) -> Any:
        spec = self.require(key)
        fn = resolve_callable(spec.handler)
        return fn(*args, **kwargs)


