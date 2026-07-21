import io
from typing import Any

from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamFile(TextstreamCommon, TextstreamBackend):
    """
    Backend for file-based (io.TextIOBase-conforming) streaming text data
    """

    _f: io.TextIOBase | None

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: io.TextIOBase, **hints: Any) -> Any:
        if not isinstance(obj, io.TextIOBase):
            return None
        if hints and hints.get("kind", "file") != "file":
            return None
        return super().__new__(cls)

    def __init__(self, obj: io.TextIOBase, **hints: Any) -> None:
        self._f = obj

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
