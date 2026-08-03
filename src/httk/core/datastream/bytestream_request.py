import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .bytestream_backend import BytestreamBackend
from .bytestream_common import BytestreamCommon
from .compression import open_compressed, validate_compression
from .network_policy import resolve_timeout


class BytestreamRequest(BytestreamCommon, BytestreamBackend):
    """
    Backend for streaming byte data fetched via a urllib.request.Request.
    """

    _request: urllib.request.Request
    _timeout: float | None
    _compression: str
    _f: io.IOBase | None
    _underlying: io.IOBase | None
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
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.IOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            resp = urllib.request.urlopen(self._request, timeout=resolve_timeout(self._timeout))
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._request.full_url).path
            opened = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if opened is not raw else None
            self._f = opened
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
