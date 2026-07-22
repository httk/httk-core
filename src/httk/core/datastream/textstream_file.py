import io
from typing import Any

from .compression import reject_text_native_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamFile(TextstreamCommon, TextstreamBackend):
    """
    Backend for file-based (io.TextIOBase-conforming) streaming text data
    """

    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: io.TextIOBase, **hints: Any) -> Any:
        if not isinstance(obj, io.TextIOBase):
            return None
        if hints and hints.get("kind", "file") != "file":
            return None
        return super().__new__(cls)

    def __init__(self, obj: io.TextIOBase, **hints: Any) -> None:
        reject_text_native_compression(hints.get("compression"))
        self._f = obj
        # Compression cannot layer under an already-decoded text stream, so nothing to chain-close.
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._f is None or self._f.closed:
            raise ValueError("I/O operation on closed stream")
        return self._f

    @property
    def name(self) -> str | None:
        self._ensure_f()
        return getattr(self._f, "name", None)

    @property
    def closed(self) -> bool:
        return self._f is None or self._f.closed
