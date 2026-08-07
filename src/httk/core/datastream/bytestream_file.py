import io
from typing import Any

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression


class BytestreamFile(BytestreamCommon, BytestreamBackend):
    r"""
    Backend for file-based (io.IOBase-conforming) streaming byte data.
    Compressed content is transparently decompressed according to the compression hint.

    :param obj: Open binary stream to adopt and close with this backend.
    :param \**hints: Backend-selection and compression hints.
    :raises ValueError: If the compression hint is unknown.
    """

    _source: io.IOBase
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: io.IOBase, **hints: Any) -> Any:
        if not isinstance(obj, io.IOBase):
            return None
        if hints and hints.get("kind", "file") != "file":
            return None
        return super().__new__(cls)

    def __init__(self, obj: io.IOBase, **hints: Any) -> None:
        self._source = obj
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        # We adopt (and hence close) the caller's stream; keep it here so close() reaches it
        # even when a decompression wrapper is layered on top and when no read ever happens.
        self._underlying = obj
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed or self._source.closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            name = getattr(self._source, "name", None)
            self._f = open_compressed(self._source, compression=self._compression, name=name)
        return self._f

    @property
    def name(self) -> str | None:
        """Return the adopted stream's name when it provides one."""
        self._ensure_f()
        return getattr(self._source, "name", None)

    @property
    def closed(self) -> bool:
        """Report whether the adopted stream is closed."""
        return self._closed or self._source.closed
