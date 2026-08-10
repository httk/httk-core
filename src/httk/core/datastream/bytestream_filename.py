import io
from pathlib import Path
from typing import Any, Self

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression


class BytestreamFilename(BytestreamCommon, BytestreamBackend):
    r"""
    Backend for streaming byte data via operations on a file specified by a filename.
    Compressed content is transparently decompressed according to the compression hint.

    :param filename: File path to open lazily for binary reading.
    :param \**hints: Backend-selection and compression hints.
    :raises ValueError: If the compression hint is unknown.
    """

    _filename: str
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    @classmethod
    def _backend_adopt(cls, obj: Any, **hints: Any) -> Self | None:
        r"""Adopt a filename when it matches this backend.

        :param obj: The object to adopt.
        :param \**hints: Backend-selection and compression hints.
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
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            raw = open(self._filename, "rb")  # noqa: SIM115  # handle escapes to backend and is closed by close()
            opened = open_compressed(raw, compression=self._compression, name=self._filename)
            self._underlying = raw if opened is not raw else None
            self._f = opened
        return self._f

    @property
    def name(self) -> str | None:
        """Return the configured filename."""
        return self._filename

    @property
    def closed(self) -> bool:
        """Report whether the filename backend is closed."""
        return self._closed
