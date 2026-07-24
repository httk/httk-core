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


from ._plugins import PluginRegistry

#: Loaders selected by file *extension* (keys are lower-case ``".ext"`` suffixes).
loaders = PluginRegistry()

#: Loaders selected by exact *basename* (keys are lower-case basenames such as
#: ``"contcar"``). A separate key namespace from :data:`loaders` so an
#: extension-less file (``POSCAR``, ``CONTCAR``) can still dispatch by name.
loader_filenames = PluginRegistry()


def register_loader(
    *,
    name: str,
    loader: str,
    extensions: tuple[str, ...] = (),
    filenames: tuple[str, ...] = (),
) -> None:
    """Register a loader under one or more file ``extensions`` and/or ``filenames``.

    ``extensions`` are matched (case-insensitively) against a file's suffix, e.g.
    ``".cif"``. ``filenames`` are exact basenames matched (case-insensitively)
    against a file's name with any recognized compression suffix stripped, e.g.
    ``"POSCAR"`` matches ``POSCAR``, ``poscar``, and ``POSCAR.bz2``.
    """
    for ext in extensions:
        loaders.register(key=ext.lower(), handler=loader, name=name)
    for filename in filenames:
        loader_filenames.register(key=filename.lower(), handler=loader, name=name)


def known_extensions() -> list[str]:
    return loaders.keys()


def known_filenames() -> list[str]:
    return loader_filenames.keys()


entry_providers = PluginRegistry()


def register_entry_provider(*, name: str, factory: str) -> None:
    """Register an :class:`~httk.core.entry_provider.EntryProvider` factory under ``name``.

    ``factory`` is a lazy ``"module:callable"`` reference to a callable that
    constructs a provider (providers need data, so applications call the factory
    themselves; the registry only records how to reach it). This mirrors
    ``register_loader``.
    """
    entry_providers.register(key=name, handler=factory, name=name)


def known_entry_providers() -> list[str]:
    return entry_providers.keys()
