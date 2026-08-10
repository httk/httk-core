import io
from pathlib import Path
from typing import Any, Self, cast

from .compression import open_compressed, validate_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamFilename(TextstreamCommon, TextstreamBackend):
    r"""
    Backend for streaming text via operations on a file specfied by a filename
    Compressed content is transparently decompressed before text decoding.

    :param filename: File path to open lazily for text reading.
    :param \**hints: Backend-selection, encoding, and compression hints.
    :raises ValueError: If the compression hint is unknown.
    """

    _filename: str
    _compression: str
    _encoding: str | None
    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a filename when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection hints.
        :return: An initialized backend, or ``None`` when ``obj`` is not accepted.
        """
        if not isinstance(obj, str | Path):
            return None
        if hints and hints.get("kind", "filename") != "filename":
            return None
        return cls(obj, **hints)

    def __init__(self, filename: str | Path, **hints: Any) -> None:
        self._filename = str(filename)
        self._compression = hints.get("compression", "extension")
        validate_compression(self._compression)
        self._encoding = hints.get("encoding")
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            raw = open(self._filename, "rb")  # noqa: SIM115  # handle escapes to backend and is closed by close()
            decompressed = open_compressed(raw, compression=self._compression, name=self._filename)
            self._underlying = raw if decompressed is not raw else None
            self._f = io.TextIOWrapper(cast(io.BufferedReader, decompressed), encoding=self._encoding or "utf-8")
        return self._f

    @property
    def name(self) -> str | None:
        """Return the configured filename."""
        return self._filename

    @property
    def closed(self) -> bool:
        """Report whether the filename backend is closed."""
        return self._closed
