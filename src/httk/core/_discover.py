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

import importlib
import importlib.util
import pkgutil


def _import_registry_packages(path, prefix: str) -> None:
    for module in sorted(pkgutil.iter_modules(path, prefix), key=lambda item: item.name):
        if not module.ispkg:
            continue
        if importlib.util.find_spec(module.name) is not None:
            importlib.import_module(module.name)


def discover_and_register() -> None:
    """Eagerly import registration packages from the available registry tiers.

    The reserved ``cli``, ``entries``, ``io``, and ``schemas`` sub-namespaces
    are each walked independently. Registration packages are imported eagerly
    so installation errors fail fast, but they must only register lazy
    references: they must not resolve registries or load resource data while
    being imported.
    """
    importlib.import_module("httk.registry")

    prefix = "httk.registry."
    for namespace in ("cli", "entries", "io", "schemas"):
        namespace_name = f"{prefix}{namespace}"
        if importlib.util.find_spec(namespace_name) is None:
            continue
        namespace_module = importlib.import_module(namespace_name)
        _import_registry_packages(namespace_module.__path__, f"{namespace_name}.")
