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

from pathlib import Path
from typing import Any

from .plugins import PluginRegistry

_loaders = PluginRegistry()

def register_loader(*, name: str, loader: str, extensions: tuple[str, ...]) -> None:
    for ext in extensions:
        _loaders.register(key=ext.lower(), handler=loader, name=name)

def load(filename: str, **kwargs: Any) -> Any:
    ext = Path(filename).suffix.lower()
    if ext:
        return _loaders.dispatch(ext, filename, **kwargs)
    else:
        raise Exception("Could not deterine file type.")

def known_extensions() -> list[str]:
    return _loaders.keys()

