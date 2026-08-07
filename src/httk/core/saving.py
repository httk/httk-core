"""Dispatch local file writers and format serializers."""

import bz2
import gzip
import io
import lzma
import os
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import PurePath
from typing import Any
from urllib.parse import urlsplit

from ._plugins import PluginRegistry
from .datastream.compression import split_compression_suffix
from .register import (
    _writer_for_format,
    _writer_format,
    format_serializers,
    known_writers,
    writer_filenames,
    writers,
)


def _writer_key(name: str) -> tuple[PluginRegistry, str] | None:
    basename = PurePath(name).name
    inner, _codec = split_compression_suffix(basename)
    extension = PurePath(inner).suffix.lower()
    if extension and writers.get(extension) is not None:
        return writers, extension
    basename_key = inner.lower()
    if writer_filenames.get(basename_key) is not None:
        return writer_filenames, basename_key
    return None


def has_writer_for(name: str) -> bool:
    """Return whether ``name`` matches a registered writer key.

    :param name: Destination filename whose writer registration is checked.
    :return: Whether the name matches a registered extension or exact basename.
    """
    return _writer_key(name) is not None


def _writer_for(name: str, format: str | None) -> tuple[PluginRegistry, str]:
    if format is not None:
        selected = _writer_for_format(format)
        if selected is not None:
            return selected
        raise ValueError(
            f"No writer registered for format {format!r}. Known writers: {', '.join(known_writers()) or '(none)'}"
        )
    selected = _writer_key(name)
    if selected is not None:
        return selected
    basename = PurePath(name).name
    inner, _codec = split_compression_suffix(basename)
    raise ValueError(
        f"Could not determine how to save {name!r} (inner name {inner!r}): no writer registered for its "
        f"extension or basename. Known writers: {', '.join(known_writers()) or '(none)'}"
    )


def save(obj: Any, destination: str | os.PathLike[str], *, format: str | None = None, **kwargs: Any) -> None:
    r"""Save ``obj`` to a local destination selected by its name or ``format`` hint.

    The writer registry selects by extension first and exact basename second,
    case-insensitively after stripping one recognized compression suffix, unless
    ``format`` selects a registered writer directly. The format-serializer
    registry converts non-neutral objects before writing, and a recognized
    compression suffix wraps the destination transparently.

    :param obj: Object or neutral payload to serialize and write.
    :param destination: Local filename or path to write.
    :param format: Optional registered format name that selects the writer.
    :param \**kwargs: Additional options passed to the selected writer.
    :raises ValueError: If the destination or format has no writer, no serializer exists, or the destination is a URL.
    """
    if isinstance(destination, str) and urlsplit(destination).scheme in {"http", "https", "ftp", "file"}:
        raise ValueError("save writes local files; URL destinations are not supported")
    destination_name = os.fspath(destination)
    registry, key = _writer_for(destination_name, format)
    writer_spec = registry.require(key)
    format_tag = _writer_format(registry, key)
    if isinstance(obj, Mapping) and obj.get("format") == format_tag:
        payload = obj
    else:
        serializer = format_serializers.get(format_tag)
        if serializer is None:
            raise ValueError(f"No format serializer registered for {format_tag!r}")
        payload = format_serializers.dispatch(format_tag, obj)
    from ._plugins import resolve_callable

    with ExitStack() as stack:
        writer_destination: str | os.PathLike[str] | io.TextIOBase = destination
        _inner, codec = split_compression_suffix(PurePath(destination_name).name)
        if codec is not None:
            if codec.name == "gzip":
                writer_destination = stack.enter_context(gzip.open(destination_name, "wt", encoding="utf-8"))
            elif codec.name == "bzip2":
                writer_destination = stack.enter_context(bz2.open(destination_name, "wt", encoding="utf-8"))
            elif codec.name == "xz":
                writer_destination = stack.enter_context(lzma.open(destination_name, "wt", encoding="utf-8"))
            elif codec.name == "lzma":
                writer_destination = stack.enter_context(
                    lzma.open(destination_name, "wt", encoding="utf-8", format=lzma.FORMAT_ALONE)
                )
            else:
                raise ValueError(f"save cannot write compression codec {codec.name!r}")
        resolve_callable(writer_spec.handler)(writer_destination, payload, **kwargs)
