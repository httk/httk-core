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

"""Dispatch file loaders and optional domain adapters.

``load`` retains the neutral loader result when no domain adapter owns its
format, while installed capability modules can register adapters to provide a
one-call domain-loading experience. Callers that need the neutral payload can
use ``raw=True``.
"""

from collections.abc import Mapping
from pathlib import PurePath
from typing import Any

from .datastream.compression import split_compression_suffix
from .register import (
    format_adapters,
    known_extensions,
    known_filenames,
    loader_filenames,
    loaders,
)


def load(filename: str, *, raw: bool = False, **kwargs: Any) -> Any:
    """Load ``filename`` and adapt its neutral payload to a domain object.

    Dispatch strips at most one recognized compression suffix (``.gz``,
    ``.bz2``, ...) to obtain an *inner* name, then selects a loader by that
    inner name's extension (``.cif``, ``.poscar``, ...) or, failing that, by its
    exact basename (``POSCAR``, ``CONTCAR``; case-insensitive). The selected
    loader always receives the **original** ``filename``; loaders open it
    through the datastream layer, which transparently decompresses. By default,
    a mapping with a string ``"format"`` tag is passed to the registered domain
    adapter for that format. ``raw=True`` is the neutral-payload escape hatch.
    Payloads with unknown formats, and non-mapping loader results, pass through
    unchanged.
    """
    name = PurePath(filename).name
    inner, _codec = split_compression_suffix(name)
    ext = PurePath(inner).suffix.lower()
    if ext and loaders.get(ext) is not None:
        result = loaders.dispatch(ext, filename, **kwargs)
    else:
        basename_key = inner.lower()
        if loader_filenames.get(basename_key) is not None:
            result = loader_filenames.dispatch(basename_key, filename, **kwargs)
        else:
            raise ValueError(
                "Could not determine how to load "
                + repr(filename)
                + " (inner name "
                + repr(inner)
                + "): no loader registered for its extension or basename. "
                + "Known extensions: "
                + (", ".join(known_extensions()) or "(none)")
                + "; known filenames: "
                + (", ".join(known_filenames()) or "(none)")
                + "."
            )

    if raw or not isinstance(result, Mapping):
        return result
    format_tag = result.get("format")
    if not isinstance(format_tag, str) or format_adapters.get(format_tag) is None:
        return result
    return format_adapters.dispatch(format_tag, result)
