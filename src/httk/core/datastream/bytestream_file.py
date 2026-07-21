import io
from typing import Any

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon


class BytestreamFile(BytestreamCommon, BytestreamBackend):
    """
    Backend for file-based (io.IOBase-conforming) streaming byte data.
    """

    _f: io.IOBase | None

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, obj: io.IOBase, **hints: Any) -> Any:
        if not isinstance(obj, io.IOBase):
            return None
        if hints and hints.get("kind", "file") != "file":
            return None
        return super().__new__(cls)

    def __init__(self, obj: io.IOBase, **hints: Any) -> None:
        self._f = obj

    def _ensure_f(self) -> io.IOBase:
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
