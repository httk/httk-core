import io
from pathlib import Path
from typing import Any, Self

from ._textstream_common import TextstreamCommon
from .textstream_backend import TextstreamBackend


class TextstreamFilename(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text via operations on a file specfied by a filename
    """

    _filename: str
    _f: io.TextIOBase | None
    _closed: bool

    def __new__(cls, filename: str | Path, **hints: Any) -> Self | None:
        if not isinstance(filename, str | Path):
            return None
        if hints and hints.get("kind", "filename") != "filename":
            return None
        return super().__new__(cls)

    def __init__(self, filename: str | Path, **hints: Any) -> None:
        self._filename = str(filename)
        self._f = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            self._f = open(self._filename, "r")
        return self._f

    @property
    def name(self) -> str | None:
        return self._filename

    @property
    def closed(self) -> bool:
        return self._closed
