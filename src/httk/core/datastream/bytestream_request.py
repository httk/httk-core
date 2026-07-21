import io
import urllib.request
from typing import Any, cast

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon


class BytestreamRequest(BytestreamCommon, BytestreamBackend):
    """
    Backend for streaming byte data fetched via a urllib.request.Request.
    """

    _request: urllib.request.Request
    _timeout: float | None
    _f: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, request: urllib.request.Request, **hints: Any) -> Any:
        if not isinstance(request, urllib.request.Request):
            return None
        if hints and hints.get("kind", "request") != "request":
            return None
        return super().__new__(cls)

    def __init__(self, request: urllib.request.Request, **hints: Any) -> None:
        self._request = request
        self._timeout = hints.get("timeout")
        self._f = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            if self._timeout is None:
                resp = urllib.request.urlopen(self._request)
            else:
                resp = urllib.request.urlopen(self._request, timeout=self._timeout)
            self._f = cast(io.IOBase, resp)
        return self._f

    @property
    def name(self) -> str | None:
        return None

    @property
    def url(self) -> str:
        return self._request.full_url

    @property
    def request(self) -> urllib.request.Request:
        return self._request

    @property
    def closed(self) -> bool:
        return self._closed
