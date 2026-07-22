import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .compression import open_compressed, validate_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamRequest(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text fetched via a urllib.request.Request.
    """

    _request: urllib.request.Request
    _timeout: float | None
    _encoding: str | None
    _compression: str
    _f: io.TextIOBase | None
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
        self._encoding = hints.get("encoding")
        self._compression = hints.get("compression", "auto")
        validate_compression(self._compression)
        self._f = None
        self._underlying = None
        self._closed = False

    def _ensure_f(self) -> io.TextIOBase:
        if self._closed:
            raise ValueError("I/O operation on closed stream")
        if self._f is None:
            if self._timeout is None:
                resp = urllib.request.urlopen(self._request)
            else:
                resp = urllib.request.urlopen(self._request, timeout=self._timeout)
            encoding = self._encoding or resp.headers.get_content_charset() or "utf-8"
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._request.full_url).path
            decompressed = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if decompressed is not raw else None
            self._f = io.TextIOWrapper(cast(io.BufferedReader, decompressed), encoding=encoding)
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
