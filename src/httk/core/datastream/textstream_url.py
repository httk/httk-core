import io
import urllib.parse
import urllib.request
from typing import Any, cast

from .compression import open_compressed, validate_compression
from .textstream_backend import TextstreamBackend
from .textstream_common import TextstreamCommon

_URL_SCHEMES = ("http", "https", "ftp", "file")


class TextstreamURL(TextstreamCommon, TextstreamBackend):
    """
    Backend for streaming text fetched from a URL string.
    A bare string is interpreted as a URL when its scheme is one of http, https, ftp, or file,
    or when an explicit kind="url" hint is given.
    """

    _url: str
    _timeout: float | None
    _encoding: str | None
    _compression: str
    _f: io.TextIOBase | None
    _underlying: io.IOBase | None
    _closed: bool

    # mypy does not allow to type annotate __new__ as `Self | None` for some reason
    def __new__(cls, url: str, **hints: Any) -> Any:
        if not isinstance(url, str):
            return None
        kind = hints.get("kind")
        if kind == "url":
            if not urllib.parse.urlsplit(url).scheme:
                return None
            return super().__new__(cls)
        if kind is None and urllib.parse.urlsplit(url).scheme in _URL_SCHEMES:
            return super().__new__(cls)
        return None

    def __init__(self, url: str, **hints: Any) -> None:
        self._url = url
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
                resp = urllib.request.urlopen(self._url)
            else:
                resp = urllib.request.urlopen(self._url, timeout=self._timeout)
            encoding = self._encoding or resp.headers.get_content_charset() or "utf-8"
            raw = cast(io.IOBase, resp)
            name = urllib.parse.urlsplit(self._url).path
            decompressed = open_compressed(raw, compression=self._compression, name=name)
            self._underlying = raw if decompressed is not raw else None
            self._f = io.TextIOWrapper(cast(io.BufferedReader, decompressed), encoding=encoding)
        return self._f

    @property
    def name(self) -> str | None:
        return None

    @property
    def url(self) -> str:
        return self._url

    @property
    def closed(self) -> bool:
        return self._closed
