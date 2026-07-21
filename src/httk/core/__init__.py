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

import pkgutil

import httk

from . import _discover
from .datastream import (
    BytestreamBackend,
    BytestreamBytes,
    BytestreamBytesView,
    BytestreamCommon,
    BytestreamFile,
    BytestreamFilename,
    BytestreamFilenameView,
    BytestreamFileView,
    BytestreamLike,
    BytestreamView,
    TextstreamBackend,
    TextstreamCommon,
    TextstreamFile,
    TextstreamFilename,
    TextstreamFilenameView,
    TextstreamFileView,
    TextstreamLike,
    TextstreamString,
    TextstreamStringView,
    TextstreamView,
)
from .loading import load
from .views import Backend, View, unwrap

_discover.discover_and_register()


def _discover_modules():
    prefix = httk.__name__ + "."
    names = [m.name for m in pkgutil.iter_modules(httk.__path__, prefix) if m.ispkg]
    return names


subpackages = _discover_modules()

__all__ = [
    "load",
    "subpackages",
    "Backend",
    "View",
    "unwrap",
    "BytestreamView",
    "BytestreamFileView",
    "BytestreamFilenameView",
    "BytestreamBytesView",
    "BytestreamBackend",
    "BytestreamCommon",
    "BytestreamFile",
    "BytestreamFilename",
    "BytestreamBytes",
    "BytestreamLike",
    "TextstreamView",
    "TextstreamFileView",
    "TextstreamFilenameView",
    "TextstreamStringView",
    "TextstreamBackend",
    "TextstreamCommon",
    "TextstreamFile",
    "TextstreamFilename",
    "TextstreamString",
    "TextstreamLike",
]
