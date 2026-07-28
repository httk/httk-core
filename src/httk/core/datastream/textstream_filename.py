import io
from pathlib import Path
from typing import Any, cast

from .compression import open_compressed, validate_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamFilename(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text via operations on a file specfied by a filename
    """

    _filename: str
    _compression: str
    _encoding: str | None
    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
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
        return self._filename

    @property
    def closed(self) -> bool:
        return self._closed
