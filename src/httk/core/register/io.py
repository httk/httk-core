"""Reader, writer, adapter, and serializer registries."""

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
from collections.abc import Callable, Sequence
from pathlib import PurePath
from threading import Lock
from typing import Any

from ..datastream.compression import split_compression_suffix
from ._base import PluginRegistry, _same_callable_reference


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


#: Readers selected by file *extension* (keys are lower-case ``".ext"`` suffixes).
readers = PluginRegistry()

#: Readers selected by exact *basename* (keys are lower-case basenames such as
#: ``"contcar"``). A separate key namespace from :data:`readers` so an
#: extension-less file (``POSCAR``, ``CONTCAR``) can still dispatch by name.
reader_filenames = PluginRegistry()

#: Domain adapters selected by a reader's neutral payload ``"format"`` tag.
format_adapters = PluginRegistry()
_format_adapter_lock = Lock()

#: Writers selected by file extension or exact basename.
writers = PluginRegistry()
writer_filenames = PluginRegistry()
writer_formats = PluginRegistry()
_writer_formats: dict[tuple[int, str], str] = {}
_writers_by_format: dict[str, tuple[PluginRegistry, str]] = {}
format_serializers = PluginRegistry()
_format_serializer_lock = Lock()


def register_reader(
    *,
    name: str,
    reader: str,
    extensions: tuple[str, ...] = (),
    filenames: tuple[str, ...] = (),
) -> None:
    """Register a reader under one or more file ``extensions`` and/or ``filenames``.

    ``extensions`` are matched (case-insensitively) against a file's suffix, e.g.
    ``".cif"``. ``filenames`` are exact basenames matched (case-insensitively)
    against a file's name with any recognized compression suffix stripped, e.g.
    ``"POSCAR"`` matches ``POSCAR``, ``poscar``, and ``POSCAR.bz2``.

    :param name: The registry name for the reader.
    :param reader: A lazy ``"module:callable"`` reference to the reader.
    :param extensions: File suffixes that select the reader.
    :param filenames: Exact basenames that select the reader.
    """
    for ext in extensions:
        readers.register(key=ext.lower(), handler=reader, name=name)
    for filename in filenames:
        reader_filenames.register(key=filename.lower(), handler=reader, name=name)


def known_extensions() -> list[str]:
    """Return the registered reader extensions.

    :return: Lower-case reader suffixes.
    """
    return readers.keys()


def known_filenames() -> list[str]:
    """Return the registered reader basenames.

    :return: Lower-case reader basenames.
    """
    return reader_filenames.keys()


def register_format_adapter(
    *,
    name: str,
    adapter: str | Callable[..., Any],
    formats: Sequence[str],
) -> None:
    """Register one lazy adapter for each neutral payload format in ``formats``.

    ``adapter`` may be a callable or a lazy ``"module:callable"`` reference.
    A format tag has one owner: registering it again raises an error naming both
    the existing and attempted registrants.

    :param name: The registry name for the adapter.
    :param adapter: The adapter callable or lazy ``"module:callable"`` reference.
    :param formats: Neutral payload format tags served by the adapter.
    :raises ValueError: If a format tag is invalid, duplicated, or already owned.
    """
    if isinstance(formats, str):
        raise ValueError("formats must be a sequence of nonempty format-tag strings, not a string")
    try:
        format_tags = tuple(formats)
    except TypeError as exc:
        raise ValueError("formats must be a sequence of nonempty format-tag strings") from exc
    seen: set[str] = set()
    for format_tag in format_tags:
        if not isinstance(format_tag, str) or not format_tag:
            raise ValueError(f"format tags must be nonempty strings, got {format_tag!r}")
        if format_tag in seen:
            raise ValueError(f"format adapter format tag is listed more than once: {format_tag!r}")
        seen.add(format_tag)
    with _format_adapter_lock:
        missing: list[str] = []
        for format_tag in format_tags:
            existing = format_adapters.get(format_tag)
            if existing is None:
                missing.append(format_tag)
                continue
            if existing.name == name and _same_callable_reference(existing.handler, adapter):
                continue
            raise ValueError(
                f"format tag {format_tag!r} is already registered by {existing.name!r}; cannot register {name!r}"
            )
        for format_tag in missing:
            format_adapters.register(key=format_tag, handler=adapter, name=name)


def known_format_adapters() -> dict[str, str]:
    """Return format tags mapped to their registered adapter names.

    :return: Format tags mapped to registry names.
    """
    known: dict[str, str] = {}
    for format_tag, spec in sorted(format_adapters.items()):
        if spec.name is not None:
            known[format_tag] = spec.name
    return known


def register_writer(
    *,
    name: str,
    writer: str | Callable[..., Any],
    format: str,
    extensions: tuple[str, ...] = (),
    filenames: tuple[str, ...] = (),
) -> None:
    """Register a writer under one or more extensions and/or exact basenames.

    A format can have one writer owner; registering a conflicting writer raises
    an error. Extension and basename keys are matched case-insensitively.

    :param name: The registry name for the writer.
    :param writer: The writer callable or lazy ``"module:callable"`` reference.
    :param format: The neutral payload format emitted by the writer.
    :param extensions: File suffixes that select the writer.
    :param filenames: Exact basenames that select the writer.
    :raises ValueError: If ``format`` is invalid or conflicts with an existing writer.
    """
    if not isinstance(format, str) or not format:
        raise ValueError(f"writer format must be a nonempty string, got {format!r}")
    keys = [(writers, extension.lower()) for extension in extensions]
    keys += [(writer_filenames, filename.lower()) for filename in filenames]
    existing = _writers_by_format.get(format)
    if existing is not None:
        old = existing[0].get(existing[1])
        if old is not None and not _same_callable_reference(old.handler, writer):
            raise ValueError(f"writer format {format!r} is already registered by {old.name!r}")
    if not keys:
        writer_formats.register(key=format, handler=writer, name=name)
        _writer_formats[(id(writer_formats), format)] = format
        _reindex_writer_format(format)
        return
    affected_formats = {format}
    for registry, key in keys:
        old_format = _writer_formats.get((id(registry), key))
        if old_format is not None:
            affected_formats.add(old_format)
        registry.register(key=key, handler=writer, name=name)
        _writer_formats[(id(registry), key)] = format
    for affected_format in affected_formats:
        _reindex_writer_format(affected_format)


def known_writers() -> list[str]:
    """Return the registered writer extension and basename dispatch keys.

    :return: Writer keys selected by extensions or exact basenames.
    """
    return sorted(set(writers.keys()) | set(writer_filenames.keys()))


def known_writer_formats() -> list[str]:
    """Return registered writer format tags.

    :return: Registered neutral payload format tags.
    """
    return sorted(_writers_by_format)


def _reindex_writer_format(format: str) -> None:
    for registry in (writers, writer_filenames, writer_formats):
        for key in registry.keys():  # noqa: SIM118 — PluginRegistry exposes keys(), not mapping iteration.
            if _writer_formats.get((id(registry), key)) == format:
                _writers_by_format[format] = (registry, key)
                return
    _writers_by_format.pop(format, None)


def _writer_for_format(format: str) -> tuple[PluginRegistry, str] | None:
    return _writers_by_format.get(format)


def _writer_format(registry: PluginRegistry, key: str) -> str:
    return _writer_formats[(id(registry), key)]


def register_format_serializer(*, format: str, serializer: str | Callable[..., Any]) -> None:
    """Register one lazy serializer for a neutral payload format tag.

    :param format: The neutral payload format tag.
    :param serializer: The serializer callable or lazy reference.
    :raises ValueError: If ``format`` is invalid or already has another serializer.
    """
    if not isinstance(format, str) or not format:
        raise ValueError(f"format tag must be a nonempty string, got {format!r}")
    with _format_serializer_lock:
        existing = format_serializers.get(format)
        if existing is not None:
            if _same_callable_reference(existing.handler, serializer):
                return
            raise ValueError(f"format serializer {format!r} is already registered")
        format_serializers.register(key=format, handler=serializer, name=format)
