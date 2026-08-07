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

"""Dispatch file readers and optional domain adapters.

``load`` retains the neutral reader result when no domain adapter owns its
format, while installed capability modules can register adapters to provide a
one-call domain-loading experience. Callers that need the neutral payload can
use ``raw=True``.
"""

from collections.abc import Mapping
from pathlib import PurePath
from typing import Any
from urllib.parse import urlsplit

from ._plugins import PluginRegistry
from .datastream.compression import split_compression_suffix
from .register import (
    format_adapters,
    known_extensions,
    known_filenames,
    reader_filenames,
    readers,
)


def _reader_key(name: str) -> tuple[PluginRegistry, str] | None:
    basename = PurePath(name).name
    inner, _codec = split_compression_suffix(basename)
    ext = PurePath(inner).suffix.lower()
    if ext and readers.get(ext) is not None:
        return readers, ext
    basename_key = inner.lower()
    if reader_filenames.get(basename_key) is not None:
        return reader_filenames, basename_key
    return None


def has_reader_for(name: str) -> bool:
    """Return whether ``name`` matches a registered reader key.

    :param name: Filename or URL path whose reader registration is checked.
    :return: Whether the name matches a registered extension or exact basename.
    """
    return _reader_key(name) is not None


def reader_uses_extension(name: str) -> bool:
    """Return whether ``name`` is claimed by an extension rather than a basename.

    :param name: Filename or URL path whose reader registration is checked.
    :return: Whether an extension registration claims the name.
    """
    key = _reader_key(name)
    return key is not None and key[0] is readers


def adapt_result(result: Any, raw: bool) -> Any:
    """Apply a registered format adapter unless ``raw`` is requested.

    :param result: Neutral reader result to inspect for a format tag.
    :param raw: Whether to return the neutral result without adaptation.
    :return: The adapted domain value or the unchanged reader result.
    """
    if raw or not isinstance(result, Mapping):
        return result
    format_tag = result.get("format")
    if not isinstance(format_tag, str) or format_adapters.get(format_tag) is None:
        return result
    return format_adapters.dispatch(format_tag, result)


def load_source(source: Any, name: str, *, raw: bool = False, **kwargs: Any) -> Any:
    r"""Load ``source`` using the reader selected by ``name``.

    :param source: Source passed to the selected reader.
    :param name: Name used for extension or exact-basename dispatch.
    :param raw: Whether to return the neutral reader result without adaptation.
    :param \**kwargs: Additional options passed to the selected reader.
    :return: The reader result, optionally adapted to a domain value.
    :raises ValueError: If no reader matches the name; the error lists known extensions and basenames.
    """
    key = _reader_key(name)
    if key is None:
        basename = PurePath(name).name
        inner, _codec = split_compression_suffix(basename)
        raise ValueError(
            "Could not determine how to load "
            + repr(name)
            + " (inner name "
            + repr(inner)
            + "): no reader registered for its extension or basename. "
            + "Known extensions: "
            + (", ".join(known_extensions()) or "(none)")
            + "; known filenames: "
            + (", ".join(known_filenames()) or "(none)")
            + "."
        )
    registry, reader_key = key
    return adapt_result(registry.dispatch(reader_key, source, **kwargs), raw)


def load(filename: str, *, raw: bool = False, **kwargs: Any) -> Any:
    r"""Load ``filename`` and adapt its neutral payload to a domain object.

    Dispatch strips at most one recognized compression suffix (``.gz``,
    ``.bz2``, ...) to obtain an *inner* name, then selects a reader by that
    inner name's extension (``.cif``, ``.poscar``, ...) or, failing that, by its
    exact basename (``POSCAR``, ``CONTCAR``; case-insensitive). The selected
    reader always receives the **original** ``filename``; readers open it
    through the datastream layer, which transparently decompresses. By default,
    a mapping with a string ``"format"`` tag is passed to the registered domain
    adapter for that format. ``raw=True`` is the neutral-payload escape hatch.
    Payloads with unknown formats, and non-mapping reader results, pass through
    unchanged.

    :param filename: Local filename to read.
    :param raw: Whether to return the neutral reader result without adaptation.
    :param \**kwargs: Additional options passed to the selected reader.
    :return: The loaded and optionally adapted value.
    :raises ValueError: If ``filename`` is a URL or no reader matches it.
    """
    if isinstance(filename, str) and urlsplit(filename).scheme in {"http", "https", "ftp", "file"}:
        raise ValueError("load reads local files; httk.core.fetch(url) is the URL entry point")
    return load_source(filename, filename, raw=raw, **kwargs)
