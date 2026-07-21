import io
from pathlib import Path
from typing import Any

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon


class BytestreamFilename(BytestreamCommon, BytestreamBackend):
    """
    Backend for streaming byte data via operations on a file specified by a filename.
    """

    _filename: str
    _f: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, filename: str | Path, **hints: Any) -> Any:
        if not isinstance(filename, str | Path):
            return None
        if hints and hints.get("kind", "filename") != "filename":
            return None
        return super().__new__(cls)

    def __init__(self, filename: str | Path, **hints: Any) -> None:
        self._filename = str(filename)
        self._f = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            self._f = open(self._filename, "rb")
        return self._f

    @property
    def name(self) -> str | None:
        return self._filename

    @property
    def closed(self) -> bool:
        return self._closed
