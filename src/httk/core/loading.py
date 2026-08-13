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

import os
from collections.abc import Generator, Iterable, Mapping
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import PurePath
from typing import Any, Literal
from urllib.parse import urlsplit

from .datastream.compression import split_compression_suffix
from .register.io import (
    _reader_key,
    format_adapters,
    has_reader_for,  # noqa: F401
    known_extensions,
    known_filenames,
    readers,
)


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


def _load_many_worker(source: Any, kwargs: dict[str, Any]) -> Any:
    """Load one source in a process-pool worker."""
    return load(source, **kwargs)


def _load_many_chunksize(sources: Iterable[Any], processes: int | None) -> int:
    workers = processes or os.cpu_count() or 1
    try:
        count = len(sources)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(1, min(32, count // (workers * 4)))


def _note_load_many_error(error: Exception, source: Any) -> None:
    if any(isinstance(note, str) and note.startswith("load_many source:") for note in getattr(error, "__notes__", ())):
        return
    error.add_note(f"load_many source: {source!r}")


def _load_many_serial(source: Any, kwargs: dict[str, Any], errors: Literal["raise", "return"]) -> Any:
    try:
        return load(source, **kwargs)
    except Exception as error:
        _note_load_many_error(error, source)
        if errors == "return":
            return error
        raise


def load_many(
    sources: Iterable[Any],
    *,
    processes: int | None = None,
    errors: Literal["raise", "return"] = "raise",
    **kwargs: Any,
) -> Generator[tuple[Any, Any], None, None]:
    r"""Load multiple sources lazily, preserving input order.

    ``processes=None`` uses the process-pool default. ``processes=0`` or
    ``processes=1`` loads in the current process, which is also the guaranteed
    path for readers registered at runtime. Parallel workers rediscover
    installed registration packages, but runtime registrations are not
    guaranteed to be present in a fresh worker. Parallel work uses bounded
    ordered futures rather than :meth:`~concurrent.futures.Executor.map` so
    worker failures and result-pickling failures can be returned per source.

    :param sources: Sources accepted by :func:`load`.
    :param processes: Number of worker processes, or ``None`` for the default.
    :param errors: Whether to raise failures or yield them as exception values.
    :param \**kwargs: Options forwarded to every :func:`load` call.
    :return: A lazy iterator of ``(source, result)`` pairs in input order.
    :raises ValueError: If ``errors`` is not ``"raise"`` or ``"return"``, or if
        ``processes`` is negative.
    :raises TypeError: If ``processes`` is not an integer or ``None``.
    """
    if errors not in {"raise", "return"}:
        raise ValueError("errors must be 'raise' or 'return'")
    if processes is not None and (isinstance(processes, bool) or not isinstance(processes, int)):
        raise TypeError("processes must be an integer or None")
    if processes is not None and processes < 0:
        raise ValueError("processes must be non-negative")

    if processes in (0, 1):
        for source in sources:
            try:
                result = load(source, **kwargs)
            except Exception as error:
                _note_load_many_error(error, source)
                if errors == "return":
                    yield source, error
                    continue
                raise
            yield source, result
        return

    chunksize = _load_many_chunksize(sources, processes)
    workers = processes or os.cpu_count() or 1
    pending_limit = max(1, min(32, workers * chunksize))
    with ProcessPoolExecutor(max_workers=processes) as executor:
        pending: dict[int, tuple[Any, Future[Any] | None]] = {}
        source_iterator = iter(sources)
        next_index = 0
        next_result = 0
        exhausted = False
        pool_broken = False
        while pending or not exhausted:
            while not pool_broken and not exhausted and len(pending) < pending_limit:
                try:
                    source = next(source_iterator)
                except StopIteration:
                    exhausted = True
                    break
                try:
                    future = executor.submit(_load_many_worker, source, kwargs)
                except Exception as error:
                    _note_load_many_error(error, source)
                    if errors == "raise":
                        raise
                    pool_broken = True
                    pending[next_index] = (source, None)
                    next_index += 1
                    break
                pending[next_index] = (source, future)
                next_index += 1

            if not pending:
                if pool_broken:
                    for source in source_iterator:
                        yield source, _load_many_serial(source, kwargs, errors)
                break
            source, future = pending.pop(next_result)
            next_result += 1
            if future is None:
                yield source, _load_many_serial(source, kwargs, errors)
                continue
            try:
                result = future.result()
            except BrokenProcessPool as error:
                pool_broken = True
                _note_load_many_error(error, source)
                if errors == "return":
                    yield source, error
                    continue
                raise
            except Exception as error:
                _note_load_many_error(error, source)
                if errors == "return":
                    yield source, error
                    continue
                raise
            yield source, result
