import io
from typing import Any

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression


class BytestreamBytes(BytestreamCommon, BytestreamBackend):
    """
    Backend for streaming byte data backed by an actual bytes object.
    """

    b: bytes
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # Cannot type annotate __new__ as `Self | None` for some reason
    def __new__(cls, content: bytes | bytearray, **hints: Any) -> Any:
        if not isinstance(content, bytes | bytearray):
            return None
        if hints and hints.get("kind", "content") != "content":
            return None
        return super().__new__(cls)

    def __init__(self, content: bytes | bytearray, **hints: Any) -> None:
        self.b = bytes(content)
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            raw: io.IOBase = io.BytesIO(self.b)
            opened = open_compressed(raw, compression=self._compression, name=None)
            self._underlying = raw if opened is not raw else None
            self._f = opened
        return self._f

    @property
    def name(self) -> str | None:
        return None

    @property
    def closed(self) -> bool:
        return self._closed
