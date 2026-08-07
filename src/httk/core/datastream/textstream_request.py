import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .compression import open_compressed, validate_compression
from .network_policy import resolve_timeout
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon


class TextstreamRequest(TextstreamCommon, TextstreamBackend):
    r"""
    Backend for streaming text fetched via a urllib.request.Request.
    Response content is transparently decompressed before text decoding.

    :param request: Request to execute lazily when text is first read.
    :param \**hints: Backend-selection, encoding, timeout, and compression hints.
    :raises ValueError: If the compression hint is unknown.
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
            resp = urllib.request.urlopen(self._request, timeout=resolve_timeout(self._timeout))
            encoding = self._encoding or resp.headers.get_content_charset() or "utf-8"
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._request.full_url).path
            decompressed = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if decompressed is not raw else None
            self._f = io.TextIOWrapper(cast(io.BufferedReader, decompressed), encoding=encoding)
        return self._f

    @property
    def name(self) -> str | None:
        """Report that a request backend has no filename."""
        return None

    @property
    def url(self) -> str:
        """Return the request URL."""
        return self._request.full_url

    @property
    def request(self) -> urllib.request.Request:
        """Return the request used to fetch the stream."""
        return self._request

    @property
    def closed(self) -> bool:
        """Report whether the request backend is closed."""
        return self._closed
