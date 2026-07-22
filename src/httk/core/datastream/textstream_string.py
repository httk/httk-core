import io
from typing import Any

from .compression import reject_text_native_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamString(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text backed by an actual string
    """

    s: str
    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # Cannot type annotate __new__ as `Self | None` for some reason
    def __new__(cls, content: str, **hints: Any) -> Any:
        if not isinstance(content, str):
            return None
        if hints and hints.get("kind", "content") != "content":
            return None
        return super().__new__(cls)

    def __init__(self, content: str, **hints: Any) -> None:
        reject_text_native_compression(hints.get("compression"))
        self.s = content
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            self._f = io.StringIO(self.s)
        return self._f

    @property
    def name(self) -> str | None:
        return None

    @property
    def closed(self) -> bool:
        return self._closed
